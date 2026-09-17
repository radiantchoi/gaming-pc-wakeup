# Puts this PC to sleep (S3). Never hibernates.
# Installed on the gaming PC as the action of the "gaming-pc-sleep" scheduled
# task, which the server triggers over SSH with "schtasks /run". See README.

Add-Type -Namespace Win32 -Name Power -MemberDefinition @'
[DllImport("powrprof.dll", SetLastError = true)]
public static extern bool SetSuspendState(bool hibernate, bool forceCritical, bool disableWakeEvent);
'@

# Give the SSH session that triggered the task a moment to close cleanly.
Start-Sleep -Seconds 2

[void][Win32.Power]::SetSuspendState($false, $false, $false)
