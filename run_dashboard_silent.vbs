Option Explicit

Dim shell, fso, root, pythonw, dashboard, userKey, command

Set shell = CreateObject("WScript.Shell")
Set fso = CreateObject("Scripting.FileSystemObject")

root = fso.GetParentFolderName(WScript.ScriptFullName)
pythonw = root & "\.venv\Scripts\pythonw.exe"
dashboard = root & "\dashboard.py"

If Not fso.FileExists(pythonw) Then
    MsgBox "Python virtual environment was not found:" & vbCrLf & pythonw & vbCrLf & vbCrLf & _
           "Run install_windows.bat or ask Codex to install dependencies first.", _
           vbCritical, "Realtime Subtitle"
    WScript.Quit 1
End If

If Not fso.FileExists(dashboard) Then
    MsgBox "dashboard.py was not found:" & vbCrLf & dashboard, vbCritical, "Realtime Subtitle"
    WScript.Quit 1
End If

userKey = shell.Environment("USER").Item("DEEPSEEK_API_KEY")
If Len(shell.Environment("PROCESS").Item("DEEPSEEK_API_KEY")) = 0 And Len(userKey) > 0 Then
    shell.Environment("PROCESS").Item("DEEPSEEK_API_KEY") = userKey
End If

shell.CurrentDirectory = root
command = """" & pythonw & """ """ & dashboard & """"
shell.Run command, 0, False
