# Navigator suite: one-time cleanup of the plugin folders used before 30 October 2026.
#
# The suite's folders were renamed (for example Systems_Navigator -> Navigator_Cartography).
# Run this once, with EDMC closed, after extracting the new plugins. It:
#   - copies anything an old folder kept that the new version does not ship (such as Voice
#     backups) into the matching new folder, without overwriting anything;
#   - moves each old folder into plugins\_Navigator_old_backup (EDMC ignores that folder);
#   - leaves an old folder alone if its new version is not installed, so nothing disappears.
# Nothing is deleted. To undo, move a folder back out of _Navigator_old_backup.
#
# Usage: double-click Navigator_Cleanup.bat. Optional: -PluginsPath <folder>  -WhatIf

param([string]$PluginsPath = "", [switch]$WhatIf)
$ErrorActionPreference = "Stop"

$Renames = [ordered]@{
    "Systems_Navigator"                  = "Navigator_Cartography"
    "Ship_Computer"                      = "Navigator_Dashboard"
    "Docking_Navigator"                  = "Navigator_Docking"
    "Ship_Radio"                         = "Navigator_Radio"
    "Voice_Navigator"                    = "Navigator_Voice"
    "Neutron_Highway_Navigator"          = "Navigator_Neutron_Highway"
    "Neutron_Highway_Navigator_Auto"     = "Navigator_Neutron_Highway_Auto"
}
# Files every plugin ships; anything else in an old folder is user data worth keeping.
$CodeExtensions = @(".py", ".pyc", ".cs", ".exe", ".txt", ".md", ".json.bak")
$Shipped = @("LICENSE", "NOTICE.txt", "README.txt", "README.md", "recipes.json", "engineers.json")

function Find-PluginsFolder {
    if ($PluginsPath) { return $PluginsPath }
    $here = Split-Path -Parent $PSScriptRoot          # when run from plugins\_Navigator_Cleanup
    if (Test-Path (Join-Path $here "Navigator_Interface")) { return $here }
    return Join-Path $env:LOCALAPPDATA "EDMarketConnector\plugins"
}

$plugins = Find-PluginsFolder
Write-Host "Navigator folder cleanup" -ForegroundColor Cyan
Write-Host "Plugins folder: $plugins"
if (-not (Test-Path $plugins)) { Write-Host "That folder does not exist. Nothing changed." -ForegroundColor Red; exit 1 }
if (Get-Process EDMarketConnector -ErrorAction SilentlyContinue) {
    Write-Host "EDMC is running. Close EDMC, then run this again. Nothing changed." -ForegroundColor Yellow; exit 2
}
if ($WhatIf) { Write-Host "Preview only (-WhatIf): nothing will be changed." -ForegroundColor Yellow }
# Any other route edition follows the same pattern: Neutron_Highway_Navigator_X -> Navigator_Neutron_Highway_X.
Get-ChildItem $plugins -Directory -Filter "Neutron_Highway_Navigator_*" | Where-Object { -not $Renames.Contains($_.Name) } |
    ForEach-Object { $Renames[$_.Name] = "Navigator_Neutron_Highway_" + $_.Name.Substring("Neutron_Highway_Navigator_".Length) }

$stamp = Get-Date -Format "yyyyMMdd_HHmmss"
$backup = Join-Path $plugins "_Navigator_old_backup"
$moved = 0; $kept = 0; $copied = 0
foreach ($old in $Renames.Keys) {
    $new = $Renames[$old]
    $oldPath = Join-Path $plugins $old
    $newPath = Join-Path $plugins $new
    if (-not (Test-Path $oldPath)) { continue }
    if (-not (Test-Path (Join-Path $newPath "load.py"))) {
        Write-Host "  $old : kept, because $new is not installed. Install it first to replace this." -ForegroundColor Yellow
        $kept++; continue
    }
    # Carry over user files (e.g. Voice Backups) that the new version does not ship.
    Get-ChildItem $oldPath -Recurse -File | Where-Object {
        $_.FullName -notmatch '\\__pycache__\\' -and $_.Extension -notin $CodeExtensions -and $_.Name -notin $Shipped
    } | ForEach-Object {
        $relative = $_.FullName.Substring($oldPath.Length + 1)
        $target = Join-Path $newPath $relative
        if (-not (Test-Path $target)) {
            if (-not $WhatIf) {
                New-Item -ItemType Directory -Force (Split-Path $target) | Out-Null
                Copy-Item $_.FullName $target
            }
            Write-Host "  $old : copied $relative into $new"
            $copied++
        }
    }
    $destination = Join-Path $backup "${old}_$stamp"
    if (-not $WhatIf) {
        New-Item -ItemType Directory -Force $backup | Out-Null
        Move-Item $oldPath $destination
    }
    Write-Host "  $old : moved to _Navigator_old_backup (replaced by $new)" -ForegroundColor Green
    $moved++
}
Write-Host ""
if ($moved -eq 0 -and $kept -eq 0) { Write-Host "No old Navigator folders found. Nothing to do." -ForegroundColor Green }
else { Write-Host "Done: $moved moved, $copied file(s) carried over, $kept kept. Start EDMC when ready." -ForegroundColor Cyan }
exit 0
