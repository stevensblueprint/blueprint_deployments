# Architecture Overview

The `blueprint_deployments` project is an automated infrastructure-as-code system designed to provision, manage, and destroy static website environments on AWS. It uses **AWS CDK** to define the infrastructure and **GitHub Actions** for content deployment.

## High-Level Architecture

The system operates as a **Control Plane** that manages multiple independent website deployments.

1.  **API Gateway**: The entry point for external systems to request new deployments or deletions.
2.  **State Management**: The configuration for all deployed websites is stored in a single JSON object within **AWS Secrets Manager** (the `Infrastructure Config` secret).
3.  **Observability**: The system provides endpoints to list all active deployments and poll the real-time status of the provisioning pipeline, including stage-by-stage updates.
4.  **CI/CD Pipeline**: An **AWS CodePipeline** (defined in `PipelineStack`) is triggered whenever the configuration changes. It dynamically generates CloudFormation stacks for each website defined in the configuration.
4.  **GitHub Integration**:
    *   **Repo Creation**: The system automatically creates new GitHub repositories for each website based on a template.
    *   **Secret Injection**: Upon successful infrastructure provisioning, the system injects necessary AWS credentials and configuration (e.g., S3 Bucket Name, CloudFront ID) into the GitHub repository's secrets.
    *   **Content Deployment**: A GitHub Action workflow (`deploy.yml`) in the created repository uses these secrets to build and sync the website content to S3.

## Key Components

### 1. Pipeline Stack (`lib/stacks/pipeline-stack.ts`)
The central CDK stack that defines the deployment pipeline. It orchestrates the entire system and provisions the shared resources.

*   **Responsibility**:
    *   Sets up the `BaseDeploymentConstruct` which contains the CodePipeline.
    *   Provisions the `ApiDeployConstruct` (The "Trigger").
    *   Provisions the `DeploymentNotifyConstruct` (The "Feedback Loop").

### 2. API Deploy Construct (`lib/constructs/api-deploy-construct.ts`)
Exposes the REST API that allows users (or other systems) to control the infrastructure.

*   **Resources**: API Gateway, `deploy-api-function` Lambda.
*   **Functionality**:
    *   Validates incoming requests.
    *   Updates the `Infrastructure Config` in Secrets Manager.
    *   Creates/Deletes GitHub repositories.
    *   Triggers the CodePipeline to apply changes.

### 3. Deployment Notify Construct (`lib/constructs/deployment-notify-construct.ts`)
Closes the loop between AWS infrastructure provisioning and application code deployment.

*   **Resources**: EventBridge Rule, `notify-deployment-function` Lambda.
*   **Functionality**:
    *   Listens for `CloudFormation Stack Status Change` events.
    *   Filters for stacks created by this blueprint (starting with `blueprint-`).
    *   When a stack is successfully created/updated, it fetches the stack outputs (S3 bucket, CloudFront ID).
    *   Updates the corresponding GitHub repository secrets.
    *   Triggers the `deploy.yml` workflow in GitHub.

## Data Flow

1.  **Request**: User `POST /deploy` -> API Gateway.
2.  **Update**: Lambda adds site to Secrets Manager & creates GitHub Repo.
3.  **Provision**: CodePipeline detects change -> CloudFormation creates S3/CloudFront.
4.  **Notify**: EventBridge detects Stack Complete -> Notify Lambda.
5.  **Deploy**: Notify Lambda updates GitHub Secrets -> GitHub Action deploys content to S3.
