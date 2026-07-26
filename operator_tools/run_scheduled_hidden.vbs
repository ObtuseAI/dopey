Option Explicit

Dim commandKey
Dim commandNames
Dim commandPath
Dim exitCode
Dim fileSystem
Dim scriptDirectory
Dim shell

If WScript.Arguments.Count <> 1 Then
    WScript.Quit 87
End If

commandKey = LCase(Trim(CStr(WScript.Arguments(0))))
Set commandNames = CreateObject("Scripting.Dictionary")
commandNames.CompareMode = 1
commandNames.Add "acceleration_cycle", "acceleration_cycle.cmd"
commandNames.Add "daily_ritual", "daily_ritual.cmd"
commandNames.Add "intraday", "intraday.cmd"
commandNames.Add "live_branch", "live_branch.cmd"
commandNames.Add "monday_preflight", "monday_preflight.cmd"
commandNames.Add "nightly", "nightly.cmd"
commandNames.Add "research_supervisor", "research_supervisor.cmd"
commandNames.Add "weekend_soak", "weekend_soak.cmd"

If Not commandNames.Exists(commandKey) Then
    WScript.Quit 87
End If

Set fileSystem = CreateObject("Scripting.FileSystemObject")
scriptDirectory = fileSystem.GetParentFolderName(WScript.ScriptFullName)
commandPath = fileSystem.BuildPath(scriptDirectory, commandNames.Item(commandKey))
If Not fileSystem.FileExists(commandPath) Then
    WScript.Quit 2
End If

Set shell = CreateObject("WScript.Shell")
exitCode = shell.Run(Chr(34) & commandPath & Chr(34), 0, True)
WScript.Quit exitCode
