Option Explicit
Dim fs, sh, root, py, command
Set fs = CreateObject("Scripting.FileSystemObject")
Set sh = CreateObject("WScript.Shell")
root = fs.GetParentFolderName(WScript.ScriptFullName)
py = root & "\.venv\Scripts\pythonw.exe"
If Not fs.FileExists(py) Then
  py = sh.ExpandEnvironmentStrings("%USERPROFILE%") & "\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\pythonw.exe"
End If
If Not fs.FileExists(py) Then
  MsgBox "Python runtime not found. Please see README.md to install the local environment.", 48, "文枢"
  WScript.Quit 1
End If
sh.CurrentDirectory = root
command = Chr(34) & py & Chr(34) & " -X utf8 " & Chr(34) & root & "\launch.py" & Chr(34)
sh.Run command, 0, False
