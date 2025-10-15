#!/usr/bin/env pwsh
<#
.SYNOPSIS
    Quick test script for AI Agent training - simplified version
#>

param(
    [string]$ApiKey = "jareer",
    [string]$BaseUrl = "http://localhost:8000"
)

Write-Host "🚀 Quick AI Agent Training Test" -ForegroundColor Magenta

# 1. Health Check
Write-Host "`n1. Health Check..." -ForegroundColor Yellow
try {
    $response = Invoke-WebRequest -Uri "$BaseUrl/api/healthz" -Method GET
    Write-Host "✅ API is healthy!" -ForegroundColor Green
} catch {
    Write-Host "❌ API not responding. Start server with: uvicorn app.main:app --reload" -ForegroundColor Red
    exit 1
}

# 2. Upload CSV
Write-Host "`n2. Uploading CSV..." -ForegroundColor Yellow
try {
    $file = Get-Item "AI Agent Training (Messages) - Full conversations.csv"
    $boundary = [System.Guid]::NewGuid().ToString()
    $LF = "`r`n"
    
    $bodyLines = (
        "--$boundary",
        "Content-Disposition: form-data; name=`"file`"; filename=`"$($file.Name)`"",
        "Content-Type: text/csv$LF",
        [System.IO.File]::ReadAllText($file.FullName),
        "--$boundary--$LF"
    ) -join $LF
    
    $headers = @{ 
        "X-API-Key" = $ApiKey
        "Content-Type" = "multipart/form-data; boundary=$boundary"
    }
    
    $response = Invoke-WebRequest -Uri "$BaseUrl/api/training/ingest-csv" -Method POST -Headers $headers -Body $bodyLines
    Write-Host "✅ CSV uploaded successfully!" -ForegroundColor Green
    Write-Host $response.Content -ForegroundColor Cyan
} catch {
    Write-Host "❌ CSV upload failed: $($_.Exception.Message)" -ForegroundColor Red
}

# 3. Train RAG
Write-Host "`n3. Training RAG..." -ForegroundColor Yellow
try {
    $headers = @{ "X-API-Key" = $ApiKey }
    $response = Invoke-WebRequest -Uri "$BaseUrl/api/training/train-rag" -Method POST -Headers $headers
    Write-Host "✅ RAG training completed!" -ForegroundColor Green
    Write-Host $response.Content -ForegroundColor Cyan
} catch {
    Write-Host "❌ RAG training failed: $($_.Exception.Message)" -ForegroundColor Red
}

# 4. Check Stats
Write-Host "`n4. Checking dataset stats..." -ForegroundColor Yellow
try {
    $headers = @{ "X-API-Key" = $ApiKey }
    $response = Invoke-WebRequest -Uri "$BaseUrl/api/training/dataset-stats" -Method GET -Headers $headers
    Write-Host "✅ Stats retrieved!" -ForegroundColor Green
    Write-Host $response.Content -ForegroundColor Cyan
} catch {
    Write-Host "❌ Stats check failed: $($_.Exception.Message)" -ForegroundColor Red
}

Write-Host "`n🎉 Quick test completed!" -ForegroundColor Magenta
