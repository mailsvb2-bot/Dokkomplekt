$ErrorActionPreference = 'Stop'
$PSNativeCommandUseErrorActionPreference = $true

$setup = Get-ChildItem -Path '.\dist\Dokkomplekt-Setup-*.exe' | Sort-Object Name | Select-Object -Last 1
if (-not $setup) { throw 'Installer artifact not found.' }

$installDir = Join-Path $env:RUNNER_TEMP 'Dokkomplekt-Installer-Smoke'
if (Test-Path $installDir) { Remove-Item -Recurse -Force $installDir }

$agent = $null
try {
    $install = Start-Process -FilePath $setup.FullName -ArgumentList @(
        '/VERYSILENT', '/SUPPRESSMSGBOXES', '/NORESTART', "/DIR=$installDir"
    ) -Wait -PassThru
    if ($install.ExitCode -ne 0) { throw "Silent install failed: $($install.ExitCode)" }

    $exe = Join-Path $installDir 'MedicalDiaryAutofill.exe'
    if (-not (Test-Path $exe)) { throw 'Installed EXE is missing.' }

    $bundleCheck = Start-Process -FilePath $exe -ArgumentList '--check-runtime-bundle' -Wait -PassThru
    if ($bundleCheck.ExitCode -ne 0) { throw "Installed EXE runtime-bundle smoke failed: $($bundleCheck.ExitCode)" }

    $psi = New-Object System.Diagnostics.ProcessStartInfo
    $psi.FileName = $exe
    $psi.Arguments = '--intake-agent'
    $psi.UseShellExecute = $false
    $psi.CreateNoWindow = $true
    $agent = [System.Diagnostics.Process]::Start($psi)
    Start-Sleep -Seconds 3
    if ($agent.HasExited) { throw "Intake agent exited before uninstall smoke: $($agent.ExitCode)" }

    $uninstaller = Get-ChildItem -Path $installDir -Filter 'unins*.exe' | Select-Object -First 1
    if (-not $uninstaller) { throw 'Inno Setup uninstaller is missing.' }
    $uninstall = Start-Process -FilePath $uninstaller.FullName -ArgumentList @(
        '/VERYSILENT', '/SUPPRESSMSGBOXES', '/NORESTART'
    ) -Wait -PassThru
    if ($uninstall.ExitCode -ne 0) { throw "Silent uninstall failed: $($uninstall.ExitCode)" }

    $agent.WaitForExit(5000) | Out-Null
    if (-not $agent.HasExited) { throw 'Background intake agent still holds the application after uninstall.' }
    if (Test-Path $exe) { throw 'Installed EXE still exists after uninstall.' }
} finally {
    if ($agent -and -not $agent.HasExited) { $agent.Kill($true) }
    if (Test-Path $installDir) { Remove-Item -Recurse -Force $installDir -ErrorAction SilentlyContinue }
}
