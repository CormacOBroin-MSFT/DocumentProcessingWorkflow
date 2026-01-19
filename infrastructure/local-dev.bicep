// Infrastructure for local development only
// Creates: Storage Account, Document Intelligence
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

// Document Intelligence
resource documentIntelligence 'Microsoft.CognitiveServices/accounts@2023-05-01' = {
  name: '${baseName}-docint'
  location: location
  sku: {
    name: 'F0' // Free tier
  }
  kind: 'FormRecognizer'
  properties: {
    publicNetworkAccess: 'Enabled'
    customSubDomainName: '${baseName}-docint'
    disableLocalAuth: false // Allow key-based auth for local dev
  }
}

// Outputs
output storageAccountName string = storageAccount.name
output documentIntelligenceEndpoint string = documentIntelligence.properties.endpoint
output documentIntelligenceName string = documentIntelligence.name
