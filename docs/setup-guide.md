# Setup Guide

This guide explains how to deploy the `blueprint_deployments` system itself.

## Prerequisites

*   **Node.js**: v18 or later.
*   **AWS CLI**: Configured with Administrator access to your AWS account.
*   **AWS CDK**: Installed globally (`npm install -g aws-cdk`).
*   **GitHub Personal Access Token (PAT)**: With permissions to create repositories and manage secrets.
*   **AWS CodeConnection**: A connection between your AWS account and GitHub organization must be established in the AWS Console.

## Configuration

The system is configured via environment variables. Create a `.env` file in the root directory (or set these in your CI/CD environment):

| Variable | Description |
| :--- | :--- |
| `PIPELINE_NAME` | A unique name for your CodePipeline (e.g., `blueprint-pipeline`). |
| `GITHUB_REPO_OWNER` | The GitHub organization or username where this blueprint repo lives. |
| `GITHUB_REPO_NAME` | The name of this blueprint repository. |
| `CODE_CONNECTION_ARN` | The ARN of the AWS CodeConnection for GitHub. |

**Example `.env`:**
```bash
PIPELINE_NAME=my-deployment-system
GITHUB_REPO_OWNER=my-org
GITHUB_REPO_NAME=blueprint-deployments
CODE_CONNECTION_ARN=arn:aws:codestar-connections:us-east-1:123456789012:connection/abcdef-1234-5678-9012
```

## Deployment Steps

1.  **Install Dependencies**
    ```bash
    npm install
    ```

2.  **Bootstrap CDK** (If this is your first time using CDK in this region)
    ```bash
    cdk bootstrap
    ```

3.  **Deploy the Pipeline**
    ```bash
    cdk deploy
    ```

## Post-Deployment

After the initial deployment:

1.  **Locate the API URL**: Check the CloudFormation outputs for `ApiDeployUrl`.
2.  **Add Configuration and Secrets**:
    *   **Infrastructure Config**: Find the secret named `<PIPELINE_NAME>-env-variables`. This secret stores the global configuration for the deployment system (account IDs, domain names, etc.) as well as the registry of deployed websites.
    *   **GitHub OAuth Token**: Find the secret named `<PIPELINE_NAME>-github-oauth-token`. Update the secret value (Plaintext) with your **GitHub PAT**. This is required for the Lambdas to interact with the GitHub API.

## Troubleshooting

*   **Lambda Errors**: Check CloudWatch Logs for `ApiLambdaFunction` or `GitHubUpdaterLambda`.
*   **Pipeline Failures**: Check the AWS CodePipeline console for build or deployment errors.
*   **GitHub Issues**: Ensure your PAT has the `repo`, `workflow`, and `admin:org` (if applicable) scopes.
