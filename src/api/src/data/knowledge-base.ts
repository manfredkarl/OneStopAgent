import type { Scenario, SampleEstimate, ReferenceArchitecture } from '../models/index.js';

export const scenarios: Scenario[] = [
  {
    id: 'SCN-001',
    title: 'Digital Commerce Platform',
    industry: 'Retail',
    description:
      'End-to-end digital commerce solution enabling omnichannel retail experiences with unified inventory, personalized recommendations, and seamless checkout across web, mobile, and in-store.',
    link: 'https://learn.microsoft.com/en-us/azure/architecture/guide/architecture-styles/web-queue-worker',
    tags: ['e-commerce', 'omnichannel', 'digital', 'storefront', 'retail', 'shopping', 'POS', 'inventory'],
  },
  {
    id: 'SCN-002',
    title: 'Digital Transformation using AI',
    industry: 'Cross-Industry',
    description:
      'Modernize legacy systems and business processes with AI-powered automation, intelligent document processing, and predictive analytics across any industry vertical.',
    link: 'https://learn.microsoft.com/en-us/azure/architecture/ai-ml/guide/data-science-and-machine-learning',
    tags: ['AI', 'machine learning', 'modernization', 'digital', 'transformation', 'automation'],
  },
  {
    id: 'SCN-003',
    title: 'Patient Portal & Telehealth',
    industry: 'Healthcare',
    description:
      'Secure patient engagement platform with telehealth video visits, appointment scheduling, medical records access, and remote monitoring integration for hospitals and clinics.',
    link: 'https://learn.microsoft.com/en-us/industry/healthcare/architecture/patient-access',
    tags: ['patient', 'telehealth', 'hospital', 'clinical', 'EHR', 'medical', 'HIPAA', 'health'],
  },
  {
    id: 'SCN-004',
    title: 'Remote Patient Monitoring',
    industry: 'Healthcare',
    description:
      'IoT-based remote patient monitoring platform that collects vitals from wearable devices, enables telehealth consultations, and provides real-time alerts to care teams.',
    link: 'https://learn.microsoft.com/en-us/azure/architecture/solution-ideas/articles/telehealth-system',
    tags: ['IoT', 'telehealth', 'patient', 'monitoring', 'hospital', 'medical', 'wearable', 'health'],
  },
  {
    id: 'SCN-005',
    title: 'Smart Factory IoT Platform',
    industry: 'Manufacturing',
    description:
      'Connected factory solution with IoT sensors, digital twins, predictive maintenance, and real-time production monitoring for Industry 4.0 manufacturing environments.',
    link: 'https://learn.microsoft.com/en-us/azure/architecture/guide/iiot-guidance/iiot-architecture',
    tags: ['factory', 'IoT', 'predictive maintenance', 'production', 'supply chain', 'OT', 'manufacturing', 'assembly'],
  },
  {
    id: 'SCN-006',
    title: 'Fraud Detection & Prevention',
    industry: 'Financial Services',
    description:
      'Real-time fraud detection system using machine learning models, anomaly detection, and transaction scoring to protect financial institutions from fraudulent activities.',
    link: 'https://learn.microsoft.com/en-us/azure/architecture/ai-ml/architecture/real-time-fraud-detection',
    tags: ['fraud', 'bank', 'fintech', 'real-time analytics', 'anomaly detection', 'security', 'compliance', 'financial'],
  },
  {
    id: 'SCN-007',
    title: 'Citizen Services Portal',
    industry: 'Public Sector',
    description:
      'Unified digital government platform enabling citizens to access services online, submit applications, track requests, and interact with government agencies securely.',
    link: 'https://learn.microsoft.com/en-us/azure/architecture/guide/data/data-lake-warehouse',
    tags: ['government', 'citizen', 'public sector', 'digital services', 'portal', 'compliance'],
  },
  {
    id: 'SCN-008',
    title: 'Data Analytics & BI Platform',
    industry: 'Cross-Industry',
    description:
      'Enterprise-grade analytics and business intelligence platform with data warehousing, interactive dashboards, and self-service reporting powered by Azure Synapse and Power BI.',
    link: 'https://learn.microsoft.com/en-us/azure/architecture/solution-ideas/articles/azure-databricks-modern-analytics-architecture',
    tags: ['analytics', 'BI', 'data', 'reporting', 'dashboard', 'insights', 'data warehouse'],
  },
  {
    id: 'SCN-009',
    title: 'Intelligent Claims Processing',
    industry: 'Financial Services',
    description:
      'AI-powered claims automation pipeline for insurance companies that extracts data from documents, validates claims, and accelerates processing with minimal human intervention.',
    link: 'https://learn.microsoft.com/en-us/azure/architecture/ai-ml/architecture/automate-document-classification-durable-functions',
    tags: ['insurance', 'claims', 'automation', 'AI', 'fintech', 'compliance', 'financial'],
  },
  {
    id: 'SCN-010',
    title: 'Predictive Maintenance Platform',
    industry: 'Manufacturing',
    description:
      'IoT and ML-based predictive maintenance solution that analyzes sensor data to forecast equipment failures and optimize maintenance schedules in manufacturing plants.',
    link: 'https://learn.microsoft.com/en-us/azure/architecture/ai-ml/idea/predictive-maintenance',
    tags: ['IoT', 'predictive maintenance', 'factory', 'production', 'OT', 'manufacturing', 'analytics'],
  },
];

export const sampleEstimates: SampleEstimate[] = [
  {
    id: 'EST-001',
    title: 'Calgary Connected Commerce',
    customerName: 'Calgary Co-op',
    industry: 'Retail',
    description:
      'Omnichannel commerce platform connecting 400+ retail locations with unified inventory, mobile ordering, and curbside pickup powered by Azure App Service and Cosmos DB.',
    link: undefined,
    estimatedACR: 420000,
  },
  {
    id: 'EST-002',
    title: 'Costco Phase 2 Digital Transform',
    customerName: 'Costco',
    industry: 'Retail',
    description:
      'Phase 2 of digital transformation initiative migrating legacy warehouse management and e-commerce systems to Azure microservices architecture with AKS and Azure SQL.',
    link: undefined,
    estimatedACR: 1200000,
  },
  {
    id: 'EST-003',
    title: 'New Balance Project Dawn',
    customerName: 'New Balance',
    industry: 'Retail',
    description:
      'Direct-to-consumer digital commerce platform with personalized shopping experiences, AI-driven recommendations, and global CDN deployment on Azure.',
    link: undefined,
    estimatedACR: 680000,
  },
  {
    id: 'EST-004',
    title: 'HSBC Fraud Detection System',
    customerName: 'HSBC',
    industry: 'Financial Services',
    description:
      'Real-time fraud detection and prevention system processing millions of transactions daily using Azure Databricks, Event Hubs, and custom ML models.',
    link: undefined,
    estimatedACR: 890000,
  },
  {
    id: 'EST-005',
    title: 'Cleveland Clinic Telehealth',
    customerName: 'Cleveland Clinic',
    industry: 'Healthcare',
    description:
      'Enterprise telehealth platform enabling virtual visits, remote patient monitoring, and secure health data exchange with HIPAA-compliant Azure infrastructure.',
    link: undefined,
    estimatedACR: 540000,
  },
  {
    id: 'EST-006',
    title: 'Siemens Smart Factory',
    customerName: 'Siemens',
    industry: 'Manufacturing',
    description:
      'Industry 4.0 smart factory deployment with IoT Edge devices, Azure Digital Twins, and predictive maintenance analytics across 12 manufacturing plants.',
    link: undefined,
    estimatedACR: 1500000,
  },
  {
    id: 'EST-007',
    title: 'NYC Digital Services',
    customerName: 'NYC Government',
    industry: 'Public Sector',
    description:
      'Citizen-facing digital services portal consolidating 50+ city services with secure identity verification, case management, and Azure Government cloud deployment.',
    link: undefined,
    estimatedACR: 720000,
  },
  {
    id: 'EST-008',
    title: 'Contoso Insurance Claims AI',
    customerName: 'Contoso Insurance',
    industry: 'Financial Services',
    description:
      'AI-powered claims processing pipeline reducing claim cycle time by 60% using Azure AI Document Intelligence, Logic Apps, and Azure SQL.',
    link: undefined,
    estimatedACR: 350000,
  },
  {
    id: 'EST-009',
    title: 'Fabrikam Health Monitoring',
    customerName: 'Fabrikam Health',
    industry: 'Healthcare',
    description:
      'Remote patient health monitoring system using IoT wearables and Azure IoT Hub to track vitals and trigger automated clinical workflows.',
    link: undefined,
    estimatedACR: 290000,
  },
];

export const referenceArchitectures: ReferenceArchitecture[] = [
  {
    id: 'ARCH-001',
    title: 'Microservices-Based E-Commerce Platform',
    description:
      'Cloud-native e-commerce platform using microservices architecture with AKS for container orchestration, Cosmos DB for product catalog, and API Management for unified API gateway.',
    link: 'https://learn.microsoft.com/en-us/azure/architecture/microservices/',
    azureServices: ['Azure Kubernetes Service', 'Cosmos DB', 'API Management', 'Azure Front Door'],
  },
  {
    id: 'ARCH-002',
    title: 'Scalable E-Commerce Web App',
    description:
      'Scalable web application architecture for e-commerce with App Service for hosting, Azure SQL for transactional data, Redis cache for performance, and CDN for global content delivery.',
    link: 'https://learn.microsoft.com/en-us/azure/architecture/web-apps/app-service/architectures/baseline-zone-redundant',
    azureServices: ['App Service', 'Azure SQL', 'Azure Cache for Redis', 'CDN'],
  },
  {
    id: 'ARCH-003',
    title: 'AI-Powered Customer Service',
    description:
      'Intelligent customer service solution using Azure AI Document Intelligence and Cognitive Services to automate document processing, with Blob Storage and Logic Apps for workflow orchestration.',
    link: 'https://learn.microsoft.com/en-us/azure/architecture/ai-ml/architecture/conversational-bot',
    azureServices: ['Azure AI Document Intelligence', 'Cognitive Services', 'Blob Storage', 'Logic Apps'],
  },
  {
    id: 'ARCH-004',
    title: 'IoT Reference Architecture',
    description:
      'Comprehensive IoT solution architecture with IoT Hub for device management, Stream Analytics for real-time processing, Digital Twins for spatial modeling, and Time Series Insights for historical analytics.',
    link: 'https://learn.microsoft.com/en-us/azure/architecture/reference-architectures/iot',
    azureServices: ['IoT Hub', 'Stream Analytics', 'Azure Digital Twins', 'Time Series Insights'],
  },
  {
    id: 'ARCH-005',
    title: 'Healthcare Data Platform',
    description:
      'HIPAA-compliant healthcare data platform for aggregating clinical data, enabling analytics, and supporting telehealth workloads with Azure API for FHIR, Azure Synapse, and Power BI.',
    link: 'https://learn.microsoft.com/en-us/industry/healthcare/architecture/healthcare-data',
    azureServices: ['Azure API for FHIR', 'Azure Synapse Analytics', 'Power BI', 'Azure Data Lake Storage'],
  },
  {
    id: 'ARCH-006',
    title: 'Financial Services Analytics',
    description:
      'Real-time and batch analytics architecture for financial services with Event Hubs for transaction ingestion, Databricks for ML, Synapse for warehousing, and Power BI for reporting.',
    link: 'https://learn.microsoft.com/en-us/azure/architecture/industries/finance/',
    azureServices: ['Event Hubs', 'Azure Databricks', 'Azure Synapse Analytics', 'Power BI'],
  },
  {
    id: 'ARCH-007',
    title: 'Government Cloud Architecture',
    description:
      'Secure government cloud architecture designed for FedRAMP and IL5 compliance with Azure Government, Azure Active Directory, Key Vault, and Azure Monitor for comprehensive governance.',
    link: 'https://learn.microsoft.com/en-us/azure/azure-government/documentation-government-overview-azure',
    azureServices: ['Azure Government', 'Azure Active Directory', 'Key Vault', 'Azure Monitor'],
  },
  {
    id: 'ARCH-008',
    title: 'Real-Time Fraud Detection',
    description:
      'Real-time fraud detection architecture processing streaming transactions with Event Hubs, running ML scoring via Azure Databricks, and storing results in Azure Synapse for investigation.',
    link: 'https://learn.microsoft.com/en-us/azure/architecture/ai-ml/architecture/real-time-fraud-detection',
    azureServices: ['Event Hubs', 'Azure Databricks', 'Azure Synapse Analytics', 'Power BI'],
  },
];
