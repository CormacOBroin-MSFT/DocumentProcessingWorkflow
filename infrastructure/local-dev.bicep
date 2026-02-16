// Infrastructure for local development only
// Creates: Storage Account, Microsoft Foundry (new) resource + project + GPT model deployment, Azure AI Search, Cosmos DB
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

// Microsoft Foundry (new) resource - uses AIServices kind with allowProjectManagement
// This creates a Foundry resource compatible with the new Foundry portal (ai.azure.com with toggle on)
resource aiFoundry 'Microsoft.CognitiveServices/accounts@2025-06-01' = {
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
    // Required for new Foundry - defines the developer API endpoint subdomain
    customSubDomainName: '${baseName}-foundry'
    // Enable local auth for development (can be disabled in production)
    disableLocalAuth: false
    // CRITICAL: This enables the new Foundry project management capabilities
    allowProjectManagement: true
  }
}

// Microsoft Foundry Project - child resource of the Foundry account
// Projects group in/outputs for a use case, including files, agents, evaluations, etc.
// This creates a project visible in the new Foundry portal
resource aiProject 'Microsoft.CognitiveServices/accounts/projects@2025-06-01' = {
  name: '${baseName}-project'
  parent: aiFoundry
  location: location
  identity: {
    type: 'SystemAssigned'
  }
  properties: {}
}

// GPT-4.1 Model Deployment (required for Content Understanding and LLM tasks)
resource gpt41Deployment 'Microsoft.CognitiveServices/accounts/deployments@2025-06-01' = {
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

// GPT-4.1-mini Model Deployment (faster, lower cost option)
resource gpt41MiniDeployment 'Microsoft.CognitiveServices/accounts/deployments@2025-06-01' = {
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
resource embeddingDeployment 'Microsoft.CognitiveServices/accounts/deployments@2025-06-01' = {
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

// Azure AI Search Service for agent tools (HS codes, sanctions lookup)
// This integrates natively with Foundry agents via AzureAISearchAgentTool
resource searchService 'Microsoft.Search/searchServices@2024-06-01-preview' = {
  name: '${baseName}-search'
  location: location
  sku: {
    name: 'basic'  // Basic tier supports semantic search
  }
  identity: {
    type: 'SystemAssigned'
  }
  properties: {
    hostingMode: 'default'
    publicNetworkAccess: 'enabled'
    partitionCount: 1
    replicaCount: 1
    semanticSearch: 'standard'  // Enable semantic search for better results
    // Enable RBAC authentication (required for DefaultAzureCredential)
    authOptions: {
      aadOrApiKey: {
        aadAuthFailureMode: 'http401WithBearerChallenge'
      }
    }
  }
}

// Cosmos DB Account for storing processed customs declarations
// Using serverless capacity mode for cost-effective local development
resource cosmosDbAccount 'Microsoft.DocumentDB/databaseAccounts@2024-05-15' = {
  name: '${baseName}-cosmos'
  location: location
  kind: 'GlobalDocumentDB'
  properties: {
    databaseAccountOfferType: 'Standard'
    consistencyPolicy: {
      defaultConsistencyLevel: 'Session'
    }
    locations: [
      {
        locationName: location
        failoverPriority: 0
        isZoneRedundant: false
      }
    ]
    capabilities: [
      {
        name: 'EnableServerless'
      }
    ]
    publicNetworkAccess: 'Enabled'
  }
}

// Cosmos DB Database
resource cosmosDatabase 'Microsoft.DocumentDB/databaseAccounts/sqlDatabases@2024-05-15' = {
  parent: cosmosDbAccount
  name: 'customs-workflow'
  properties: {
    resource: {
      id: 'customs-workflow'
    }
  }
}

// Cosmos DB Container for customs declarations
// Partition key on documentId for efficient single-document operations
resource cosmosContainer 'Microsoft.DocumentDB/databaseAccounts/sqlDatabases/containers@2024-05-15' = {
  parent: cosmosDatabase
  name: 'declarations'
  properties: {
    resource: {
      id: 'declarations'
      partitionKey: {
        paths: ['/documentId']
        kind: 'Hash'
      }
      indexingPolicy: {
        automatic: true
        indexingMode: 'consistent'
      }
    }
  }
}

// Outputs
output storageAccountName string = storageAccount.name
output contentUnderstandingEndpoint string = aiFoundry.properties.endpoint
output aiServicesName string = aiFoundry.name
output aiProjectName string = aiProject.name
output openAIEndpoint string = aiFoundry.properties.endpoint
output openAIDeploymentName string = gpt41Deployment.name
output searchServiceName string = searchService.name
output searchServiceEndpoint string = 'https://${searchService.name}.search.windows.net'
output cosmosDbEndpoint string = cosmosDbAccount.properties.documentEndpoint
output cosmosDbAccountName string = cosmosDbAccount.name
