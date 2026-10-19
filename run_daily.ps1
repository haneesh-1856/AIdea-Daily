# The daily run, as the Windows scheduled task "AI news podcast daily run" starts it at 5:00 in the morning.
# It makes today's episode from everything collected since the last run. What it printed is kept in runs\scheduled.
# Nothing is published: the package waits in out\<date> for you to review.

$root = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $root
$env:PYTHONIOENCODING = 'utf-8'
$logs = Join-Path $root 'runs\scheduled'
New-Item -ItemType Directory -Force $logs | Out-Null
$log = Join-Path $logs ((Get-Date -Format 'yyyy-MM-dd') + '.log')

# Keep the laptop awake, with the screen on, until the run ends. Left idle at 5:00 it is throttled: the voice step ran
# at 0.5 to 0.9 times real time on the scheduled runs of 13 to 19 October, against 1.9 to 2.8 with someone at the
# laptop. On 19 October it also went into standby when unplugged at 5:57, which froze the run until 6:24. The
# request ends with this script; closing the lid still puts the laptop to sleep.
Add-Type -Namespace AINews -Name Power -MemberDefinition '[DllImport("kernel32.dll")] public static extern uint SetThreadExecutionState(uint flags);'
$continuous, $system, $display = [uint32]'0x80000000', [uint32]'0x1', [uint32]'0x2'
[AINews.Power]::SetThreadExecutionState($continuous -bor $system -bor $display) | Out-Null

"Started $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')" | Out-File $log -Append -Encoding utf8
& (Join-Path $root '.venv\Scripts\python.exe') -m steps 2>&1 | ForEach-Object { "$_" } | Out-File $log -Append -Encoding utf8
$code = $LASTEXITCODE
"Finished $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss') with exit code $code" | Out-File $log -Append -Encoding utf8
[AINews.Power]::SetThreadExecutionState($continuous) | Out-Null
exit $code
