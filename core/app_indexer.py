import os
import subprocess
import webbrowser
import urllib.parse

class AppIndexer:
    """Indexa e busca aplicativos reais instalados no Windows."""

    _cached_apps = None

    @classmethod
    def _scan_apps(cls) -> list:
        if cls._cached_apps is not None:
            return cls._cached_apps

        apps = []
        seen_names = set()

        # Utilitários Essenciais do Windows sempre presentes
        system_tools = [
            ("Visual Studio Code", "code", "Desenvolvimento"),
            ("Terminal / PowerShell", "powershell", "Desenvolvimento"),
            ("Explorador de Arquivos", "explorer", "Sistema"),
            ("Gerenciador de Tarefas", "taskmgr", "Sistema"),
            ("Configurações do Windows", "start ms-settings:", "Sistema"),
            ("Calculadora", "calc", "Utilitários"),
            ("Bloco de Notas", "notepad", "Utilitários"),
        ]

        for name, cmd, cat in system_tools:
            apps.append({"name": name, "cmd": cmd, "category": cat, "type": "system"})
            seen_names.add(name.lower())

        # Varredura do Menu Iniciar (ProgramData e AppData)
        search_dirs = [
            os.path.expandvars(r"%PROGRAMDATA%\Microsoft\Windows\Start Menu\Programs"),
            os.path.expandvars(r"%APPDATA%\Microsoft\Windows\Start Menu\Programs")
        ]

        skip_keywords = ["uninstall", "desinstalar", "help", "readme", "leia-me", "configurações de", "ferramentas"]

        for base_dir in search_dirs:
            if not os.path.exists(base_dir):
                continue
            for root, _, files in os.walk(base_dir):
                for f in files:
                    if f.lower().endswith(".lnk"):
                        app_name = f[:-4].strip()
                        app_name_lower = app_name.lower()

                        if any(skip in app_name_lower for skip in skip_keywords):
                            continue
                        if app_name_lower in seen_names:
                            continue

                        full_path = os.path.join(root, f)
                        seen_names.add(app_name_lower)
                        apps.append({
                            "name": app_name,
                            "cmd": full_path,
                            "category": "Aplicativo",
                            "type": "shortcut"
                        })

        cls._cached_apps = apps
        return apps

    @classmethod
    def search(cls, query: str) -> list:
        all_apps = cls._scan_apps()
        query = query.strip()
        if not query:
            # Retorna os 5 primeiros mais úteis
            return all_apps[:5]

        q_lower = query.lower()
        results = []

        # 1. Busca nos aplicativos instalados
        for app in all_apps:
            if q_lower in app["name"].lower():
                results.append(app)
                if len(results) >= 5:
                    break

        # 2. Se for link web
        if q_lower.startswith(("http://", "https://")) or ("." in q_lower and " " not in q_lower):
            url = query if query.startswith("http") else f"https://{query}"
            results.insert(0, {
                "name": f"Abrir site: {query}",
                "cmd": f"url:{url}",
                "category": "Navegador",
                "type": "web"
            })

        # 3. Opção de pesquisa no Google
        encoded = urllib.parse.quote_plus(query)
        results.append({
            "name": f"Pesquisar no Google: '{query}'",
            "cmd": f"url:https://www.google.com/search?q={encoded}",
            "category": "Pesquisa Web",
            "type": "search"
        })

        # 4. Executar comando direto
        if len(query) >= 2 and not query.startswith("url:"):
            results.append({
                "name": f"Executar comando: '{query}'",
                "cmd": query,
                "category": "Comando do Sistema",
                "type": "command"
            })

        return results[:6]

    @staticmethod
    def launch(cmd: str) -> bool:
        try:
            if cmd.startswith("url:"):
                webbrowser.open(cmd[4:])
                return True
            elif cmd.lower().endswith(".lnk"):
                os.startfile(cmd)
                return True
            elif cmd.startswith("start "):
                os.system(cmd)
                return True
            else:
                subprocess.Popen(cmd, shell=True)
                return True
        except Exception:
            return False
