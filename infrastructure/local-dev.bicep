// Infrastructure for local development only
// Creates: Storage Account, Microsoft Foundry (new) resource + project + GPT model deployment
// Does NOT create: App Service, Key Vault (not needed locally)

@description('Base name for all resources')
param baseName string = 'autonomousflow'

@description('Azure region')
param location string = resourceGroup().location

// Storage Account
resource storageAccount 'Microsoft.Storage/storageAccounts@2023-01-01' = {
  name: '${replace(baseName, '-', '')}storage'
  location: location
  sku: {
    name: 'Standard_LRS'
  }
  kind: 'StorageV2'
  properties: {
    accessTier: 'Hot'
    allowBlobPublicAccess: false
    minimumTlsVersion: 'TLS1_2'
  }
}

resource blobService 'Microsoft.Storage/storageAccounts/blobServices@2023-01-01' = {
  parent: storageAccount
  name: 'default'
}

resource container 'Microsoft.Storage/storageAccounts/blobServices/containers@2023-01-01' = {
  parent: blobService
  name: 'customs-documents'
}

// Microsoft Foundry (new) resource
resource aiFoundry 'Microsoft.CognitiveServices/accounts@2025-04-01-preview' = {
  name: '${baseName}-foundry'
  location: location
  sku: {
    name: 'S0'
  }
  kind: 'AIServices'
  identity: {
    type: 'SystemAssigned'
  }
  properties: {
    publicNetworkAccess: 'Enabled'
    customSubDomainName: '${baseName}-foundry'
    disableLocalAuth: false
    allowProjectManagement: true
  }
}

// Note: Foundry project is created via CLI in setup-azure.sh after account is ready
// This avoids ARM timing issues with managed identity propagation

// GPT-4.1 Model Deployment (required for Content Understanding)
resource gpt41Deployment 'Microsoft.CognitiveServices/accounts/deployments@2025-04-01-preview' = {
  parent: aiFoundry
  name: 'gpt-41'
  sku: {
    name: 'GlobalStandard'
    capacity: 10
  }
  properties: {
    model: {
      format: 'OpenAI'
      name: 'gpt-4.1'
      version: '2025-04-14'
    }
    raiPolicyName: 'Microsoft.Default'
  }
}

// GPT-4.1-mini Model Deployment (required for Content Understanding)
resource gpt41MiniDeployment 'Microsoft.CognitiveServices/accounts/deployments@2025-04-01-preview' = {
  parent: aiFoundry
  name: 'gpt-41-mini'
  dependsOn: [gpt41Deployment]
  sku: {
    name: 'GlobalStandard'
    capacity: 10
  }
  properties: {
    model: {
      format: 'OpenAI'
      name: 'gpt-4.1-mini'
      version: '2025-04-14'
    }
    raiPolicyName: 'Microsoft.Default'
  }
}

// Text Embedding Model Deployment (required for Content Understanding)
resource embeddingDeployment 'Microsoft.CognitiveServices/accounts/deployments@2025-04-01-preview' = {
  parent: aiFoundry
  name: 'text-embedding-3-large'
  dependsOn: [gpt41MiniDeployment]
  sku: {
    name: 'Standard'
    capacity: 10
  }
  properties: {
    model: {
      format: 'OpenAI'
      name: 'text-embedding-3-large'
      version: '1'
    }
  }
}

// Outputs
output storageAccountName string = storageAccount.name
output contentUnderstandingEndpoint string = aiFoundry.properties.endpoint
output aiServicesName string = aiFoundry.name
output openAIEndpoint string = aiFoundry.properties.endpoint
output openAIDeploymentName string = gpt41Deployment.name
