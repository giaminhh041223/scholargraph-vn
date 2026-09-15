[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [ValidatePattern('^SG-\d{3}$')]
    [string]$TaskId
)

# Read-only lookup. Does not claim a task or configure an app model.
$ErrorActionPreference = 'Stop'
$projectRoot = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..'))
$board = Get-Content -LiteralPath (Join-Path $projectRoot 'management/tasks.json') -Raw -Encoding UTF8 | ConvertFrom-Json
$routing = Get-Content -LiteralPath (Join-Path $projectRoot 'management/model_routing.json') -Raw -Encoding UTF8 | ConvertFrom-Json
$chats = Get-Content -LiteralPath (Join-Path $projectRoot 'management/chat_registry.json') -Raw -Encoding UTF8 | ConvertFrom-Json
$task = @($board.tasks | Where-Object { $_.id -eq $TaskId })
$route = @($routing.tasks | Where-Object { $_.task_id -eq $TaskId })
if ($task.Count -ne 1 -or $route.Count -ne 1) { throw "Task/routing must exist exactly once: $TaskId" }
$task = $task[0]
$route = $route[0]
$primary = $routing.profiles.($route.primary_profile)
$review = $routing.profiles.($route.review_profile)
$lane = $chats.lanes | Where-Object { $_.chat_id -eq $route.chat_id }
$pending = @()
foreach ($dep in $task.dependencies) {
    $prerequisite = @($board.tasks | Where-Object { $_.id -eq $dep })
    if ($prerequisite.Count -ne 1 -or $prerequisite[0].status -ne 'DONE') { $pending += $dep }
}
$ready = $task.status -eq 'TODO' -and $pending.Count -eq 0
Write-Output "$($task.id) - $($task.title)"
Write-Output "Status: $($task.status); dependencies satisfied and TODO: $ready"
Write-Output "Primary recommendation: $($primary.model) / $($primary.reasoning)"
Write-Output "Lane: $($lane.chat_id) - $($lane.name)"
Write-Output "Review: $($review.model) / $($review.reasoning); $($route.review_mode)"
Write-Output "Human approval required: $($route.human_approval_required)"
Write-Output "Dependencies: $($task.dependencies -join ', '); pending: $($pending -join ', ')"
Write-Output "Reason: $($route.rationale)"
Write-Output "Task card: docs/TASKS.md#$($TaskId.ToLowerInvariant())"
Write-Output 'Start: management/templates/CHAT_START.md; read AGENTS and HANDOFF first.'
Write-Output 'Advisory only: no model change, no task claim, no thread creation.'
