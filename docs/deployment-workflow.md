# Deployment Workflow

This document details the end-to-end workflow of the `blueprint_deployments` system, from the initial API call to the live website.

## Phase 1: Initiation (The API Call)

1.  **User Action**: A `POST /deploy` request is sent to the API Gateway.
2.  **Validation**: The API Gateway model validates the JSON schema.
3.  **Lambda Processing (`deploy-api-function`)**:
    *   **Load Config**: Fetches the current state from Secrets Manager.
    *   **Create Repo**: Calls the GitHub API to create a new repository from a template.
    *   **Update State**: Adds the new website definition to the JSON config object.
    *   **Save State**: Puts the updated JSON back into Secrets Manager.
    *   **Trigger Pipeline**: Calls `codepipeline:StartPipelineExecution`.

## Phase 2: Infrastructure Provisioning (The CDK Pipeline)

1.  **Source**: CodePipeline pulls the latest source code of *this* blueprint project.
2.  **Build/Synth**: The CDK app runs. It reads the **updated** configuration from Secrets Manager.
    *   It sees the new website entry.
    *   It generates a `WebsiteStack` for that entry (defining S3, CloudFront, Route53, etc.).
3.  **Deploy**: CodePipeline deploys the CloudFormation stacks.
    *   A new stack `blueprint-<name>-website-stack` is created.

## Phase 3: The Handshake (Notify & Configure)

1.  **Event Detected**: CloudFormation emits a `CREATE_COMPLETE` event for the new stack.
2.  **Rule Match**: EventBridge captures this event because it matches the `blueprint-` prefix.
3.  **Lambda Processing (`notify-deployment-function`)**:
    *   **Identify**: Parses the stack name to find the website name.
    *   **Lookup**: Finds the corresponding repository name from the `Infrastructure Config`.
    *   **Fetch Outputs**: Queries CloudFormation for the stack's outputs:
        *   `S3BucketName`
        *   `CloudFrontDistributionId`
    *   **Configure GitHub**: Calls GitHub API to set repository secrets:
        *   `S3_BUCKET`
        *   `DISTRIBUTION_ID`
        *   `AWS_REGION`
        *   `AWS_ACCOUNT_ID`
    *   **Trigger Workflow**: Dispatches a `repository_dispatch` event or triggers the `deploy.yml` workflow in the new repo.

## Phase 4: Content Deployment (GitHub Actions)

1.  **Workflow Start**: The `deploy.yml` workflow in the *newly created* repository starts.
2.  **Build**: It installs dependencies (e.g., `npm install`) and builds the static site (e.g., `npm run build`).
3.  **Sync**: It uses the `S3_BUCKET` secret to sync the build artifacts to the S3 bucket.
4.  **Invalidate**: It uses the `DISTRIBUTION_ID` secret to invalidate the CloudFront cache.
5.  **Live**: The website is now live and updated.
