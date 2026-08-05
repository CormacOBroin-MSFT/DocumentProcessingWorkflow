// Azure Bicep template for App Service ONLY
// This template deploys just the App Service and connects it to EXISTING resources
// The resources must already exist (created by local-dev.bicep via setup-azure.sh)

@description('Base name for all resources - must match setup-azure.sh')
param baseName string = 'autonomousflow'

@description('Location for all resources')
param location string = resourceGroup().location

@description('App Service SKU')
@allowed(['B1', 'B2', 'S1', 'P1v3'])
param appServiceSku string = 'B1'

// ============================================================================
// References to EXISTING resources (created by local-dev.bicep)
// ============================================================================

// Existing Storage Account
resource storageAccount 'Microsoft.Storage/storageAccounts@2023-01-01' existing = {
  name: '${replace(baseName, '-', '')}storage'
}

// Existing AI Services (Foundry)
resource aiFoundry 'Microsoft.CognitiveServices/accounts@2025-06-01' existing = {
  name: '${baseName}-foundry'
}

// Existing AI Search
resource searchService 'Microsoft.Search/searchServices@2024-06-01-preview' existing = {
  name: '${baseName}-search'
}

// Existing Cosmos DB
resource cosmosDbAccount 'Microsoft.DocumentDB/databaseAccounts@2024-05-15' existing = {
  name: '${baseName}-cosmos'
}

// Get GPT-4.1 deployment name (should be 'gpt-41')
var gptDeploymentName = 'gpt-41'

// ============================================================================
// NEW: App Service Plan and App Service
// ============================================================================
resource appServicePlan 'Microsoft.Web/serverfarms@2023-01-01' = {
  name: '${baseName}-plan'
  location: location
  sku: {
    name: appServiceSku
  }
  kind: 'linux'
  properties: {
    reserved: true
  }
}

resource appService 'Microsoft.Web/sites@2023-01-01' = {
  name: '${baseName}-app'
  location: location
  identity: {
    type: 'SystemAssigned'
  }
  properties: {
    serverFarmId: appServicePlan.id
    siteConfig: {
      linuxFxVersion: 'PYTHON|3.11'
      appCommandLine: 'gunicorn --bind 0.0.0.0:8000 --access-logfile - --error-logfile - --log-level info --capture-output run:app'
      appSettings: [
        // Storage
        {
          name: 'AZURE_STORAGE_ACCOUNT_NAME'
          value: storageAccount.name
        }
        {
          name: 'AZURE_STORAGE_CONNECTION_STRING'
          value: 'DefaultEndpointsProtocol=https;AccountName=${storageAccount.name};EndpointSuffix=${environment().suffixes.storage};AccountKey=${storageAccount.listKeys().keys[0].value}'
        }
        {
          name: 'AZURE_STORAGE_CONTAINER'
          value: 'customs-documents'
        }
        // Content Understanding (same endpoint as OpenAI)
        {
          name: 'AZURE_CONTENT_UNDERSTANDING_ENDPOINT'
          value: aiFoundry.properties.endpoint
        }
        // Azure OpenAI
        {
          name: 'AZURE_OPENAI_ENDPOINT'
          value: aiFoundry.properties.endpoint
        }
        {
          name: 'AZURE_OPENAI_DEPLOYMENT'
          value: gptDeploymentName
        }
        // Azure AI Search
        {
          name: 'AZURE_SEARCH_ENDPOINT'
          value: 'https://${searchService.name}.search.windows.net'
        }
        {
          name: 'AZURE_SEARCH_SERVICE_NAME'
          value: searchService.name
        }
        {
          name: 'AZURE_SEARCH_CONNECTION_NAME'
          value: searchService.name
        }
        // Cosmos DB
        {
          name: 'AZURE_COSMOS_ENDPOINT'
          value: cosmosDbAccount.properties.documentEndpoint
        }
        {
          name: 'AZURE_COSMOS_DATABASE'
          value: 'customs-workflow'
        }
        {
          name: 'AZURE_COSMOS_CONTAINER'
          value: 'declarations'
        }
        // AI Foundry Project (for agents)
        {
          name: 'AZURE_AI_PROJECT_ENDPOINT'
          value: 'https://${aiFoundry.properties.customSubDomainName}.services.ai.azure.com/api/projects/${baseName}-project'
        }
        {
          name: 'AZURE_AI_MODEL_DEPLOYMENT_NAME'
          value: gptDeploymentName
        }
        // Flask
        {
          name: 'SCM_DO_BUILD_DURING_DEPLOYMENT'
          value: 'true'
        }
        {
          name: 'FLASK_ENV'
          value: 'production'
        }
      ]
    }
    httpsOnly: true
  }
}

// ============================================================================
// Role Assignments for App Service Managed Identity
// ============================================================================

// Storage Blob Data Contributor
resource storageBlobContributor 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(storageAccount.id, appService.id, 'Storage Blob Data Contributor')
  scope: storageAccount
  properties: {
    roleDefinitionId: subscriptionResourceId(
      'Microsoft.Authorization/roleDefinitions',
      'ba92f5b4-2d11-453d-a403-e96b0029c9fe'
    )
    principalId: appService.identity.principalId
    principalType: 'ServicePrincipal'
  }
}

// Cognitive Services User (for Content Understanding + OpenAI)
resource cognitiveServicesUser 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(aiFoundry.id, appService.id, 'Cognitive Services User')
  scope: aiFoundry
  properties: {
    roleDefinitionId: subscriptionResourceId(
      'Microsoft.Authorization/roleDefinitions',
      'a97b65f3-24c7-4388-baec-2e87135dc908'
    )
    principalId: appService.identity.principalId
    principalType: 'ServicePrincipal'
  }
}

// Search Index Data Contributor
resource searchIndexDataContributor 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(searchService.id, appService.id, 'Search Index Data Contributor')
  scope: searchService
  properties: {
    roleDefinitionId: subscriptionResourceId(
      'Microsoft.Authorization/roleDefinitions',
      '8ebe5a00-799e-43f5-93ac-243d3dce84a7'
    )
    principalId: appService.identity.principalId
    principalType: 'ServicePrincipal'
  }
}

// Search Service Contributor
resource searchServiceContributor 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(searchService.id, appService.id, 'Search Service Contributor')
  scope: searchService
  properties: {
    roleDefinitionId: subscriptionResourceId(
      'Microsoft.Authorization/roleDefinitions',
      '7ca78c08-252a-4471-8644-bb5ff32d4ba0'
    )
    principalId: appService.identity.principalId
    principalType: 'ServicePrincipal'
  }
}

// ============================================================================
// Outputs
// ============================================================================
output appServiceUrl string = 'https://${appService.properties.defaultHostName}'
output appServiceName string = appService.name
output appServicePrincipalId string = appService.identity.principalId
