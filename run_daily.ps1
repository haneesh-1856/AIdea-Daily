# The daily run, as the Windows scheduled task "AI news podcast daily run" starts it at 5:00 in the morning.
# It makes today's episode from everything collected since the last run. What it printed is kept in runs\scheduled.
# Nothing is published: the package waits in out\<date> for you to review.

$root = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $root
$env:PYTHONIOENCODING = 'utf-8'
$logs = Join-Path $root 'runs\scheduled'
New-Item -ItemType Directory -Force $logs | Out-Null
$log = Join-Path $logs ((Get-Date -Format 'yyyy-MM-dd') + '.log')

"Started $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')" | Out-File $log -Append -Encoding utf8
& (Join-Path $root '.venv\Scripts\python.exe') -m steps 2>&1 | ForEach-Object { "$_" } | Out-File $log -Append -Encoding utf8
"Finished $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss') with exit code $LASTEXITCODE" | Out-File $log -Append -Encoding utf8
exit $LASTEXITCODE
