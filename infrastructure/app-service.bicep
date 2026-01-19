// Azure Bicep template for App Service deployment
// Deploys: App Service, Storage, Document Intelligence, Key Vault

@description('Base name for all resources')
param baseName string = 'autonomousflow'

@description('Location for all resources')
param location string = resourceGroup().location

@description('App Service SKU')
@allowed(['B1', 'B2', 'S1', 'P1v3'])
param appServiceSku string = 'B1'

// Storage Account
resource storageAccount 'Microsoft.Storage/storageAccounts@2023-01-01' = {
  name: '${replace(baseName, '-', '')}stor'
  location: location
  sku: {
    name: 'Standard_LRS'
  }
  kind: 'StorageV2'
  properties: {
    minimumTlsVersion: 'TLS1_2'
    supportsHttpsTrafficOnly: true
    allowBlobPublicAccess: false
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
    name: 'F0' // Free tier for dev, use S0 for production
  }
  kind: 'FormRecognizer'
  properties: {
    publicNetworkAccess: 'Enabled'
    customSubDomainName: '${baseName}-docint'
    disableLocalAuth: false // Allow key-based auth for local development
  }
}

// Key Vault
resource keyVault 'Microsoft.KeyVault/vaults@2023-07-01' = {
  name: '${baseName}-kv'
  location: location
  properties: {
    sku: {
      family: 'A'
      name: 'standard'
    }
    tenantId: subscription().tenantId
    enableRbacAuthorization: true
    enableSoftDelete: true
    softDeleteRetentionInDays: 7
  }
}

// App Service Plan
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

// App Service
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
      appCommandLine: 'gunicorn --bind 0.0.0.0:8000 --chdir backend run:app'
      appSettings: [
        {
          name: 'AZURE_STORAGE_ACCOUNT_NAME'
          value: storageAccount.name
        }
        {
          name: 'AZURE_STORAGE_CONTAINER'
          value: 'customs-documents'
        }
        {
          name: 'AZURE_DOCUMENT_INTELLIGENCE_ENDPOINT'
          value: documentIntelligence.properties.endpoint
        }
        {
          name: 'AZURE_KEY_VAULT_URL'
          value: keyVault.properties.vaultUri
        }
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

// Role assignments for Managed Identity
// Storage Blob Data Contributor
resource storageBlobContributor 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(storageAccount.id, appService.id, 'Storage Blob Data Contributor')
  scope: storageAccount
  properties: {
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', 'ba92f5b4-2d11-453d-a403-e96b0029c9fe')
    principalId: appService.identity.principalId
    principalType: 'ServicePrincipal'
  }
}

// Cognitive Services User
resource cognitiveServicesUser 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(documentIntelligence.id, appService.id, 'Cognitive Services User')
  scope: documentIntelligence
  properties: {
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', 'a97b65f3-24c7-4388-baec-2e87135dc908')
    principalId: appService.identity.principalId
    principalType: 'ServicePrincipal'
  }
}

// Key Vault Secrets User
resource keyVaultSecretsUser 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(keyVault.id, appService.id, 'Key Vault Secrets User')
  scope: keyVault
  properties: {
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', '4633458b-17de-408a-b874-0445c86b69e6')
    principalId: appService.identity.principalId
    principalType: 'ServicePrincipal'
  }
}

// Outputs
output appServiceUrl string = 'https://${appService.properties.defaultHostName}'
output appServiceName string = appService.name
output storageAccountName string = storageAccount.name
output keyVaultName string = keyVault.name
output keyVaultUrl string = keyVault.properties.vaultUri
output documentIntelligenceEndpoint string = documentIntelligence.properties.endpoint
