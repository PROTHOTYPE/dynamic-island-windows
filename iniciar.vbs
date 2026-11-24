Set WshShell = CreateObject("WScript.Shell")
Set fso = CreateObject("Scripting.FileSystemObject")
scriptDir = fso.GetParentFolderName(WScript.ScriptFullName)

pythonw313 = WshShell.ExpandEnvironmentStrings("%LOCALAPPDATA%\Programs\Python\Python313\pythonw.exe")
pythonw312 = WshShell.ExpandEnvironmentStrings("%LOCALAPPDATA%\Programs\Python\Python312\pythonw.exe")

If fso.FileExists(pythonw313) Then
    cmd = """" & pythonw313 & """ """ & scriptDir & "\main.py"""
ElseIf fso.FileExists(pythonw312) Then
    cmd = """" & pythonw312 & """ """ & scriptDir & "\main.py"""
Else
    cmd = "pythonw """ & scriptDir & "\main.py"""
End If

WshShell.CurrentDirectory = scriptDir
WshShell.Run cmd, 0, False
