Set WshShell = CreateObject("WScript.Shell")
Set FSO = CreateObject("Scripting.FileSystemObject")
strCurDir = FSO.GetParentFolderName(WScript.ScriptFullName)
strDataDir = WshShell.ExpandEnvironmentStrings("%LOCALAPPDATA%\AIDSE-Desktop")
strPortFile = strDataDir & "\port.txt"
strProfileDir = strDataDir & "\profile"
strErrorLog = strDataDir & "\startup_error.log"
strCrashMarker = strDataDir & "\startup_crashed.txt"
strBackendExe = strCurDir & "\dist\aidse-backend\aidse-backend.exe"

If Not FSO.FolderExists(strDataDir) Then
    On Error Resume Next
    FSO.CreateFolder(strDataDir)
    On Error GoTo 0
End If

' Helper function to test if AIDSE is responding on a given port
Function CheckAidseHealth(portNum)
    Dim http
    CheckAidseHealth = False
    On Error Resume Next
    Set http = CreateObject("MSXML2.ServerXMLHTTP.6.0")
    http.setTimeouts 800, 800, 800, 800
    http.Open "GET", "http://127.0.0.1:" & portNum & "/health", False
    http.Send
    If Err.Number = 0 Then
        If http.Status = 200 Then
            CheckAidseHealth = True
        End If
    End If
    On Error GoTo 0
    Set http = Nothing
End Function

' Helper function to check if the backend process is currently alive
Function IsBackendRunning()
    Dim colProcesses
    IsBackendRunning = False
    On Error Resume Next
    Set colProcesses = GetObject("winmgmts:").ExecQuery("Select * from Win32_Process Where Name = 'aidse-backend.exe'")
    If colProcesses.Count > 0 Then
        IsBackendRunning = True
    End If
    On Error GoTo 0
    Set colProcesses = Nothing
End Function

' 1. Check if AIDSE is ALREADY running on previous port or default 8010
targetPort = 8010
If FSO.FileExists(strPortFile) Then
    On Error Resume Next
    Set ts = FSO.OpenTextFile(strPortFile, 1)
    savedPort = Trim(ts.ReadLine())
    ts.Close
    On Error GoTo 0
    If IsNumeric(savedPort) Then
        targetPort = CInt(savedPort)
    End If
End If

alreadyRunning = CheckAidseHealth(targetPort)
If Not alreadyRunning And targetPort <> 8010 Then
    alreadyRunning = CheckAidseHealth(8010)
    If alreadyRunning Then targetPort = 8010
End If

' 2. If not already running, start backend and monitor health
If Not alreadyRunning Then
    ' Check if backend executable is present
    If Not FSO.FileExists(strBackendExe) Then
        MsgBox "Could not find AIDSE local engine executable at:" & vbCrLf & _
               strBackendExe & vbCrLf & vbCrLf & _
               "Please reinstall the application to ensure all files are present.", _
               vbCritical, "AIDSE Startup Error"
        WScript.Quit 1
    End If

    ' Pre-flight check: verify _internal runtime directory and critical system DLLs
    strInternalDir = strCurDir & "\dist\aidse-backend\_internal"
    If FSO.FolderExists(strInternalDir) Then
        criticalDlls = Array("python3.dll", "sqlite3.dll", "vcruntime140.dll")
        For Each dllName In criticalDlls
            If Not FSO.FileExists(strInternalDir & "\" & dllName) Then
                MsgBox "Critical system runtime file is missing (" & dllName & "). " & vbCrLf & _
                       "The installation may be incomplete or blocked by security software." & vbCrLf & vbCrLf & _
                       "Please reinstall AIDSE Desktop to restore all components.", _
                       vbCritical, "Missing File - AIDSE Startup Error"
                WScript.Quit 1
            End If
        Next
    End If


    ' Clear old runtime markers
    If FSO.FileExists(strPortFile) Then On Error Resume Next: FSO.DeleteFile strPortFile, True: On Error GoTo 0
    If FSO.FileExists(strErrorLog) Then On Error Resume Next: FSO.DeleteFile strErrorLog, True: On Error GoTo 0
    If FSO.FileExists(strCrashMarker) Then On Error Resume Next: FSO.DeleteFile strCrashMarker, True: On Error GoTo 0

    ' Launch backend hidden with stderr directed to startup_error.log
    cmdLine = "%COMSPEC% /c """"" & strBackendExe & """ --host 127.0.0.1 2> """ & strErrorLog & """"""
    WshShell.Run cmdLine, 0, False

    ready = False
    attempts = 0
    Do While Not ready And attempts < 120
        WScript.Sleep 500
        attempts = attempts + 1

        ' Check active port file
        If FSO.FileExists(strPortFile) Then
            On Error Resume Next
            Set ts = FSO.OpenTextFile(strPortFile, 1)
            p = Trim(ts.ReadLine())
            ts.Close
            On Error GoTo 0
            If IsNumeric(p) Then
                targetPort = CInt(p)
                If CheckAidseHealth(targetPort) Then
                    ready = True
                End If
            End If
        Else
            If CheckAidseHealth(8010) Then
                targetPort = 8010
                ready = True
            End If
        End If

        ' Early crash detection: only if process definitely died prematurely
        If attempts >= 8 And Not ready Then
            If Not IsBackendRunning() Then
                WScript.Sleep 500
                If Not IsBackendRunning() Then
                    ' Process exited unexpectedly
                    Exit Do
                End If
            End If
        End If
    Loop

    ' If backend failed to become healthy, show error dialog and quit
    If Not ready Then
        Dim errDetails, rawLog, crashLog, isBenign, extraAttempts
        errDetails = "توقف محرك الباك إند أثناء مرحلة الإقلاع أو لم يستجب لفحص الجاهزية."
        rawLog = ""
        crashLog = ""

        ' Prioritize explicit Python crash marker if present
        If FSO.FileExists(strCrashMarker) Then
            On Error Resume Next
            Set ts = FSO.OpenTextFile(strCrashMarker, 1)
            crashLog = Trim(ts.ReadAll())
            ts.Close
            On Error GoTo 0
        End If

        If FSO.FileExists(strErrorLog) Then
            On Error Resume Next
            Set ts = FSO.OpenTextFile(strErrorLog, 1)
            rawLog = Trim(ts.ReadAll())
            ts.Close
            On Error GoTo 0
        End If

        ' Filter out benign informational lines (e.g. font cache notices, info logs)
        isBenign = False
        If InStr(rawLog, "Matplotlib is building the font cache") > 0 And InStr(rawLog, "Traceback") = 0 Then
            isBenign = True
        End If

        ' If process is STILL alive and rawLog was just font cache notice, give it extra time
        If IsBackendRunning() And (isBenign Or Len(rawLog) = 0) Then
            extraAttempts = 0
            Do While Not ready And extraAttempts < 60
                WScript.Sleep 500
                extraAttempts = extraAttempts + 1
                If CheckAidseHealth(targetPort) Then
                    ready = True
                ElseIf CheckAidseHealth(8010) Then
                    targetPort = 8010
                    ready = True
                End If
            Loop
        End If

        If Not ready Then
            If Len(crashLog) > 0 Then
                errDetails = "Internal error details:" & vbCrLf & vbCrLf & Left(crashLog, 800)
            ElseIf Len(rawLog) > 0 And Not isBenign Then
                errDetails = "Recorded error details:" & vbCrLf & vbCrLf & Left(rawLog, 800)
            ElseIf IsBackendRunning() Then
                errDetails = "AIDSE engine is running but took longer than expected to respond. Please try launching again."
            End If

            MsgBox "An error occurred while starting the AIDSE local engine:" & vbCrLf & vbCrLf & _
                   errDetails & vbCrLf & vbCrLf & _
                   "Error log file path:" & vbCrLf & strErrorLog & vbCrLf & vbCrLf & _
                   "Please ensure Microsoft Visual C++ Redistributable is installed or consult support.", _
                   vbCritical, "AIDSE Engine Startup Error"
            WScript.Quit 1
        End If
    End If
End If

' 3. Launch dedicated frameless Edge desktop window pointing to active port (with fallback)
strExtDir = strProfileDir & "\Default\Extensions"
If FSO.FolderExists(strExtDir) Then
    On Error Resume Next
    FSO.DeleteFolder strExtDir, True
    On Error GoTo 0
End If

edgeFlags = " --disable-extensions --disable-sync --disable-features=msEdgeSidebarSupport,msHubApps,msEdgeCopilot,msEdgeSearchCopilotProvider,msEdgeShopping --no-first-run --no-default-browser-check"
On Error Resume Next
WshShell.Run "msedge.exe --app=""http://127.0.0.1:" & targetPort & """ --user-data-dir=""" & strProfileDir & """" & edgeFlags & " --window-size=1280,832", 1, False
If Err.Number <> 0 Then
    Err.Clear
    WshShell.Run "http://127.0.0.1:" & targetPort, 1, False
End If
On Error GoTo 0

