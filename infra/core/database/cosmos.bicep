@description('Name of the Cosmos DB account')
param accountName string

@description('Location for resources')
param location string = resourceGroup().location

@description('Tags for all resources')
param tags object = {}

@description('Principal ID for the API managed identity (Cosmos data contributor role)')
param apiPrincipalId string

// Cosmos DB account — serverless NoSQL
resource cosmosAccount 'Microsoft.DocumentDB/databaseAccounts@2024-05-15' = {
  name: accountName
  location: location
  tags: tags
  properties: {
    databaseAccountOfferType: 'Standard'
    publicNetworkAccess: 'Enabled'
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
      { name: 'EnableServerless' }
    ]
  }
}

// Database
resource cosmosDb 'Microsoft.DocumentDB/databaseAccounts/sqlDatabases@2024-05-15' = {
  name: 'onestopagent'
  parent: cosmosAccount
  properties: {
    resource: {
      id: 'onestopagent'
    }
  }
}

// Container: projects (partition key: /userId)
resource projectsContainer 'Microsoft.DocumentDB/databaseAccounts/sqlDatabases/containers@2024-05-15' = {
  name: 'projects'
  parent: cosmosDb
  properties: {
    resource: {
      id: 'projects'
      partitionKey: {
        paths: [ '/userId' ]
        kind: 'Hash'
      }
    }
  }
}

// Container: chat_messages (partition key: /projectId)
resource chatMessagesContainer 'Microsoft.DocumentDB/databaseAccounts/sqlDatabases/containers@2024-05-15' = {
  name: 'chat_messages'
  parent: cosmosDb
  properties: {
    resource: {
      id: 'chat_messages'
      partitionKey: {
        paths: [ '/projectId' ]
        kind: 'Hash'
      }
    }
  }
}

// Container: agent_state (partition key: /projectId)
resource agentStateContainer 'Microsoft.DocumentDB/databaseAccounts/sqlDatabases/containers@2024-05-15' = {
  name: 'agent_state'
  parent: cosmosDb
  properties: {
    resource: {
      id: 'agent_state'
      partitionKey: {
        paths: [ '/projectId' ]
        kind: 'Hash'
      }
    }
  }
}

// Cosmos DB Built-in Data Contributor role assignment for the API managed identity
// Role definition ID: 00000000-0000-0000-0000-000000000002
resource cosmosRoleAssignment 'Microsoft.DocumentDB/databaseAccounts/sqlRoleAssignments@2024-05-15' = {
  name: guid(cosmosAccount.id, apiPrincipalId, '00000000-0000-0000-0000-000000000002')
  parent: cosmosAccount
  properties: {
    roleDefinitionId: '${cosmosAccount.id}/sqlRoleDefinitions/00000000-0000-0000-0000-000000000002'
    principalId: apiPrincipalId
    scope: cosmosAccount.id
  }
}

@description('Cosmos DB account endpoint')
output endpoint string = cosmosAccount.properties.documentEndpoint

@description('Cosmos DB account name')
output accountName string = cosmosAccount.name
