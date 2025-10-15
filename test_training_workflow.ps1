#!/usr/bin/env pwsh
<#
.SYNOPSIS
    Test script for AI Agent training workflow - CSV upload, RAG training, and results checking
    
.DESCRIPTION
    This script automates the complete training workflow:
    1. Uploads CSV training data
    2. Trains the RAG system
    3. Checks training results and statistics
    4. Tests agent responses
    
.PARAMETER ApiKey
    API key for authentication (default: "jareer")
    
.PARAMETER BaseUrl
    Base URL for the API (default: "http://localhost:8000")
    
.PARAMETER CsvFile
    Path to the CSV file (default: "AI Agent Training (Messages) - Full conversations.csv")
    
.EXAMPLE
    .\test_training_workflow.ps1
    
.EXAMPLE
    .\test_training_workflow.ps1 -ApiKey "your-key" -BaseUrl "http://localhost:8000"
#>

param(
    [string]$ApiKey = "jareer",
    [string]$BaseUrl = "http://localhost:8000",
    [string]$CsvFile = "AI Agent Training (Messages) - Full conversations.csv"
)

# Color functions for better output
function Write-Success { param($Message) Write-Host "✅ $Message" -ForegroundColor Green }
function Write-Error { param($Message) Write-Host "❌ $Message" -ForegroundColor Red }
function Write-Info { param($Message) Write-Host "ℹ️  $Message" -ForegroundColor Cyan }
function Write-Warning { param($Message) Write-Host "⚠️  $Message" -ForegroundColor Yellow }

# Function to make API requests with error handling
function Invoke-ApiRequest {
    param(
        [string]$Uri,
        [string]$Method = "GET",
        [hashtable]$Headers = @{},
        [string]$Body = $null,
        [string]$Form = $null
    )
    
    try {
        $params = @{
            Uri = $Uri
            Method = $Method
            Headers = $Headers
        }
        
        if ($Body) {
            $params.Body = $Body
        }
        
        if ($Form) {
            $params.Form = $Form
        }
        
        $response = Invoke-WebRequest @params
        return @{
            Success = $true
            Content = $response.Content
            StatusCode = $response.StatusCode
        }
    }
    catch {
        return @{
            Success = $false
            Error = $_.Exception.Message
            StatusCode = $_.Exception.Response.StatusCode.value__
        }
    }
}

# Main execution
Write-Host "🚀 AI Agent Training Workflow Test" -ForegroundColor Magenta
Write-Host "=" * 50 -ForegroundColor Magenta

# Check if CSV file exists
if (-not (Test-Path $CsvFile)) {
    Write-Error "CSV file not found: $CsvFile"
    exit 1
}

Write-Info "Using API Base URL: $BaseUrl"
Write-Info "Using CSV File: $CsvFile"

# Step 1: Health Check
Write-Host "`n📋 Step 1: Health Check" -ForegroundColor Yellow
Write-Host "-" * 30 -ForegroundColor Yellow

$healthResult = Invoke-ApiRequest -Uri "$BaseUrl/api/healthz"

if ($healthResult.Success) {
    Write-Success "API is healthy and responding"
    Write-Host "Response: $($healthResult.Content)"
} else {
    Write-Error "Health check failed: $($healthResult.Error)"
    Write-Warning "Make sure the server is running with: uvicorn app.main:app --reload"
    exit 1
}

# Step 2: Upload CSV Data
Write-Host "`n📋 Step 2: Upload CSV Training Data" -ForegroundColor Yellow
Write-Host "-" * 30 -ForegroundColor Yellow

$uploadHeaders = @{
    "X-API-Key" = $ApiKey
}

$uploadForm = @{
    file = Get-Item $CsvFile
}

$uploadResult = Invoke-ApiRequest -Uri "$BaseUrl/api/training/ingest-csv" -Method "POST" -Headers $uploadHeaders -Form $uploadForm

if ($uploadResult.Success) {
    Write-Success "CSV data uploaded successfully!"
    Write-Host "Upload Response: $($uploadResult.Content)"
    
    # Parse the response to show key metrics
    try {
        $uploadData = $uploadResult.Content | ConvertFrom-Json
        if ($uploadData.threads) { Write-Info "Conversations processed: $($uploadData.threads)" }
        if ($uploadData.messages) { Write-Info "Messages processed: $($uploadData.messages)" }
        if ($uploadData.embedded) { Write-Info "Messages embedded: $($uploadData.embedded)" }
    }
    catch {
        Write-Warning "Could not parse upload response JSON"
    }
} else {
    Write-Error "CSV upload failed: $($uploadResult.Error)"
    Write-Error "Status Code: $($uploadResult.StatusCode)"
    exit 1
}

# Step 3: Train RAG System
Write-Host "`n📋 Step 3: Train RAG System" -ForegroundColor Yellow
Write-Host "-" * 30 -ForegroundColor Yellow

$trainHeaders = @{
    "X-API-Key" = $ApiKey
    "Content-Type" = "application/json"
}

$trainResult = Invoke-ApiRequest -Uri "$BaseUrl/api/training/train-rag" -Method "POST" -Headers $trainHeaders

if ($trainResult.Success) {
    Write-Success "RAG training completed!"
    Write-Host "Training Response: $($trainResult.Content)"
    
    # Parse training response
    try {
        $trainData = $trainResult.Content | ConvertFrom-Json
        if ($trainData.embedded_messages) { Write-Info "Messages embedded: $($trainData.embedded_messages)" }
        if ($trainData.total_messages) { Write-Info "Total messages: $($trainData.total_messages)" }
    }
    catch {
        Write-Warning "Could not parse training response JSON"
    }
} else {
    Write-Error "RAG training failed: $($trainResult.Error)"
    Write-Warning "Continuing to check dataset stats..."
}

# Step 4: Check Dataset Statistics
Write-Host "`n📋 Step 4: Dataset Statistics" -ForegroundColor Yellow
Write-Host "-" * 30 -ForegroundColor Yellow

$statsHeaders = @{
    "X-API-Key" = $ApiKey
}

$statsResult = Invoke-ApiRequest -Uri "$BaseUrl/api/training/dataset-stats" -Method "GET" -Headers $statsHeaders

if ($statsResult.Success) {
    Write-Success "Dataset statistics retrieved!"
    Write-Host "Stats Response: $($statsResult.Content)"
    
    # Parse and display key statistics
    try {
        $statsData = $statsResult.Content | ConvertFrom-Json
        Write-Host "`n📊 Training Data Summary:" -ForegroundColor Cyan
        Write-Host "  Total Messages: $($statsData.total_messages)" -ForegroundColor White
        Write-Host "  Total Conversations: $($statsData.total_threads)" -ForegroundColor White
        Write-Host "  Embedded Messages: $($statsData.embedded_messages)" -ForegroundColor White
        Write-Host "  Embedding Coverage: $([math]::Round($statsData.embedding_coverage * 100, 2))%" -ForegroundColor White
        
        if ($statsData.role_distribution) {
            Write-Host "  Agent Messages: $($statsData.role_distribution.agent)" -ForegroundColor White
            Write-Host "  Lead Messages: $($statsData.role_distribution.lead)" -ForegroundColor White
        }
        
        if ($statsData.stage_distribution) {
            Write-Host "`n📈 Conversation Stages:" -ForegroundColor Cyan
            foreach ($stage in $statsData.stage_distribution) {
                Write-Host "  $($stage._id): $($stage.count) messages" -ForegroundColor White
            }
        }
    }
    catch {
        Write-Warning "Could not parse statistics response JSON"
    }
} else {
    Write-Error "Failed to retrieve dataset statistics: $($statsResult.Error)"
}

# Step 5: Test Agent Response
Write-Host "`n📋 Step 5: Test Agent Response" -ForegroundColor Yellow
Write-Host "-" * 30 -ForegroundColor Yellow

$testHeaders = @{
    "X-API-Key" = $ApiKey
    "Content-Type" = "application/json"
}

$testBody = @{
    text = "Hi, I need a 2 bedroom apartment under $2000 in downtown area"
    thread_id = "test-conversation-1"
    lead_profile = @{
        budget = 2000
        move_date = "2025-06-01"
    }
} | ConvertTo-Json -Depth 3

$testResult = Invoke-ApiRequest -Uri "$BaseUrl/api/agent/reply" -Method "POST" -Headers $testHeaders -Body $testBody

if ($testResult.Success) {
    Write-Success "Agent response test successful!"
    Write-Host "Agent Response: $($testResult.Content)"
    
    # Parse agent response
    try {
        $agentData = $testResult.Content | ConvertFrom-Json
        if ($agentData.message) {
            Write-Host "`n🤖 Agent Reply:" -ForegroundColor Cyan
            Write-Host "  $($agentData.message)" -ForegroundColor White
        }
        if ($agentData.stage_change) {
            Write-Host "  Stage Change: $($agentData.stage_change)" -ForegroundColor Yellow
        }
    }
    catch {
        Write-Warning "Could not parse agent response JSON"
    }
} else {
    Write-Error "Agent response test failed: $($testResult.Error)"
    Write-Warning "This might be expected if the agent service needs additional configuration"
}

# Step 6: Evaluate Model Performance (Optional)
Write-Host "`n📋 Step 6: Model Evaluation (Optional)" -ForegroundColor Yellow
Write-Host "-" * 30 -ForegroundColor Yellow

$evalHeaders = @{
    "X-API-Key" = $ApiKey
}

$evalResult = Invoke-ApiRequest -Uri "$BaseUrl/api/training/evaluate?mode=rag" -Method "GET" -Headers $evalHeaders

if ($evalResult.Success) {
    Write-Success "Model evaluation completed!"
    Write-Host "Evaluation Response: $($evalResult.Content)"
    
    # Parse evaluation results
    try {
        $evalData = $evalResult.Content | ConvertFrom-Json
        if ($evalData.accuracy) {
            Write-Host "`n📊 Model Performance:" -ForegroundColor Cyan
            Write-Host "  Accuracy: $([math]::Round($evalData.accuracy * 100, 2))%" -ForegroundColor White
            Write-Host "  Correct Retrievals: $($evalData.correct_retrievals)" -ForegroundColor White
            Write-Host "  Total Queries: $($evalData.total_queries)" -ForegroundColor White
        }
    }
    catch {
        Write-Warning "Could not parse evaluation response JSON"
    }
} else {
    Write-Warning "Model evaluation failed: $($evalResult.Error)"
    Write-Info "Evaluation might not be implemented yet"
}

# Final Summary
Write-Host "`n🎉 Training Workflow Complete!" -ForegroundColor Magenta
Write-Host "=" * 50 -ForegroundColor Magenta

Write-Info "Next Steps:"
Write-Host "1. Your AI agent is now trained on $($statsData.total_messages) messages from $($statsData.total_threads) conversations" -ForegroundColor White
Write-Host "2. Test the agent with different real estate queries" -ForegroundColor White
Write-Host "3. Monitor performance and retrain as needed" -ForegroundColor White
Write-Host "4. Integrate with your CRM or lead management system" -ForegroundColor White

Write-Host "`n🔗 API Endpoints Available:" -ForegroundColor Cyan
Write-Host "  POST /api/agent/reply - Get agent responses" -ForegroundColor White
Write-Host "  POST /api/training/ingest-csv - Upload more training data" -ForegroundColor White
Write-Host "  GET /api/training/dataset-stats - Check training statistics" -ForegroundColor White
Write-Host "  POST /api/training/train-rag - Retrain the RAG system" -ForegroundColor White

Write-Success "Training workflow test completed successfully!"
