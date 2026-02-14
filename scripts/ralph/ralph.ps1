# Ralph Wiggum - Long-running AI agent loop
# Usage: .\ralph.ps1 [-Tool copilot|claude] [-MaxIterations 10]

param(
    [ValidateSet("copilot", "claude")]
    [string]$Tool = "copilot",
    [int]$MaxIterations = 10
)

$ErrorActionPreference = "Stop"

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$PrdFile = Join-Path $ScriptDir "prd.json"
$ProgressFile = Join-Path $ScriptDir "progress.txt"
$ArchiveDir = Join-Path $ScriptDir "archive"
$LastBranchFile = Join-Path $ScriptDir ".last-branch"
$PromptFile = Join-Path $ScriptDir "CLAUDE.md"

# Archive previous run if branch changed
if ((Test-Path $PrdFile) -and (Test-Path $LastBranchFile)) {
    try {
        $prd = Get-Content $PrdFile -Raw | ConvertFrom-Json
        $CurrentBranch = $prd.branchName
    } catch {
        $CurrentBranch = ""
    }
    $LastBranch = (Get-Content $LastBranchFile -Raw).Trim()

    if ($CurrentBranch -and $LastBranch -and ($CurrentBranch -ne $LastBranch)) {
        $Date = Get-Date -Format "yyyy-MM-dd"
        $FolderName = $LastBranch -replace "^ralph/", ""
        $ArchiveFolder = Join-Path $ArchiveDir "$Date-$FolderName"

        Write-Host "Archiving previous run: $LastBranch"
        New-Item -ItemType Directory -Path $ArchiveFolder -Force | Out-Null
        if (Test-Path $PrdFile) { Copy-Item $PrdFile $ArchiveFolder }
        if (Test-Path $ProgressFile) { Copy-Item $ProgressFile $ArchiveFolder }
        Write-Host "   Archived to: $ArchiveFolder"

        # Reset progress file for new run
        @("# Ralph Progress Log", "Started: $(Get-Date)", "---") | Set-Content $ProgressFile
    }
}

# Track current branch
if (Test-Path $PrdFile) {
    try {
        $prd = Get-Content $PrdFile -Raw | ConvertFrom-Json
        $CurrentBranch = $prd.branchName
    } catch {
        $CurrentBranch = ""
    }
    if ($CurrentBranch) {
        $CurrentBranch | Set-Content $LastBranchFile
    }
}

# Initialize progress file if it doesn't exist
if (-not (Test-Path $ProgressFile)) {
    @("# Ralph Progress Log", "Started: $(Get-Date)", "---") | Set-Content $ProgressFile
}

Write-Host "Starting Ralph - Tool: $Tool - Max iterations: $MaxIterations"

for ($i = 1; $i -le $MaxIterations; $i++) {
    Write-Host ""
    Write-Host "==============================================================="
    Write-Host "  Ralph Iteration $i of $MaxIterations ($Tool)"
    Write-Host "==============================================================="

    $PromptContent = Get-Content $PromptFile -Raw
    $Output = ""
    $TempOutput = [System.IO.Path]::GetTempFileName()

    try {
        if ($Tool -eq "copilot") {
            # Copilot CLI: stream plain text output line-by-line
            $LastWasTool = $false
            $process = New-Object System.Diagnostics.Process
            $process.StartInfo.FileName = "copilot"
            $process.StartInfo.Arguments = "-p `"$($PromptContent -replace '"', '\"')`" --allow-all --stream on --silent"
            $process.StartInfo.RedirectStandardOutput = $true
            $process.StartInfo.RedirectStandardError = $true
            $process.StartInfo.UseShellExecute = $false
            $process.StartInfo.CreateNoWindow = $true
            $process.Start() | Out-Null

            $reader = $process.StandardOutput
            while (-not $reader.EndOfStream) {
                $line = $reader.ReadLine()
                if (-not $line) { continue }
                Write-Host $line
                [System.IO.File]::AppendAllText($TempOutput, "$line`n")
            }

            $process.WaitForExit()
        } else {
            # Claude Code: stream-json for real-time output display
            $LastWasTool = $false
            $process = New-Object System.Diagnostics.Process
            $process.StartInfo.FileName = "claude"
            $process.StartInfo.Arguments = "--dangerously-skip-permissions -p --output-format stream-json --verbose"
            $process.StartInfo.RedirectStandardInput = $true
            $process.StartInfo.RedirectStandardOutput = $true
            $process.StartInfo.RedirectStandardError = $true
            $process.StartInfo.UseShellExecute = $false
            $process.StartInfo.CreateNoWindow = $true
            $process.Start() | Out-Null

            $process.StandardInput.Write($PromptContent)
            $process.StandardInput.Close()

            $reader = $process.StandardOutput
            while (-not $reader.EndOfStream) {
                $line = $reader.ReadLine()
                if (-not $line) { continue }

                try {
                    $json = $line | ConvertFrom-Json -ErrorAction SilentlyContinue
                    if (-not $json) { continue }

                    if ($json.type -eq "assistant" -and $json.message.content) {
                        foreach ($block in $json.message.content) {
                            if ($block.type -eq "text") {
                                # Add newline before text if last output was a tool
                                if ($LastWasTool) {
                                    Write-Host ""
                                    [System.IO.File]::AppendAllText($TempOutput, "`n")
                                }
                                Write-Host -NoNewline $block.text
                                [System.IO.File]::AppendAllText($TempOutput, $block.text)
                                $LastWasTool = $false
                            } elseif ($block.type -eq "tool_use") {
                                $toolMsg = "`n-> Using: $($block.name)"
                                Write-Host $toolMsg
                                [System.IO.File]::AppendAllText($TempOutput, $toolMsg)
                                $LastWasTool = $true
                            }
                        }
                    }
                } catch {
                    # Non-JSON line, skip
                }
            }

            $process.WaitForExit()
        }

        $Output = Get-Content $TempOutput -Raw -ErrorAction SilentlyContinue
        if (-not $Output) { $Output = "" }
    } catch {
        Write-Host "Tool execution encountered an error: $_" -ForegroundColor Red
        $Output = ""
    } finally {
        Remove-Item $TempOutput -Force -ErrorAction SilentlyContinue
    }

    # Check for completion signal
    if ($Output -match "<promise>COMPLETE</promise>") {
        Write-Host ""
        Write-Host "Ralph completed all tasks!"
        Write-Host "Completed at iteration $i of $MaxIterations"
        exit 0
    }

    Write-Host "Iteration $i complete. Continuing..."
    Start-Sleep -Seconds 2
}

Write-Host ""
Write-Host "Ralph reached max iterations ($MaxIterations) without completing all tasks."
Write-Host "Check $ProgressFile for status."
exit 1
