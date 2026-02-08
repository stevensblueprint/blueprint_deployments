# API Reference

The `blueprint_deployments` system exposes a REST API via Amazon API Gateway to manage website deployments.

## Base URL
The Base URL is output by the CDK deployment as `ApiDeployUrl`.

---

## POST /deploy

Triggers the creation of a new website deployment.

### Request Body
**Content-Type:** `application/json`

| Field | Type | Required | Description |
| :--- | :--- | :--- | :--- |
| `name` | string | Yes | Unique identifier for the website (e.g., "my-portfolio"). |
| `subdomain` | string | Yes | The subdomain where the site will be hosted. |
| `githubRepositoryName` | string | Yes | The name of the GitHub repository to be created (must be unique within the org). |
| `githubBranchName` | string | Yes | The branch to use for deployment (usually "main"). |
| `requiresAuth` | boolean | Yes | Whether the site requires authentication (implementation dependent). |
| `includeRootDomain` | boolean | Yes | Whether to include the root domain in DNS records. |

**Example:**
```json
{
  "name": "project-alpha",
  "subdomain": "alpha",
  "githubRepositoryName": "project-alpha-repo",
  "githubBranchName": "main",
  "requiresAuth": false,
  "includeRootDomain": false
}
```

### Behavior
1.  **Config Update:** Appends the new website configuration to the `Infrastructure Config` secret in AWS Secrets Manager.
2.  **Repo Creation:** Creates a new private GitHub repository `organization/project-alpha-repo` using the configured template (e.g., Vite).
3.  **Pipeline Trigger:** Starts the AWS CodePipeline execution to provision the infrastructure.

### Response
*   **200 OK**: Deployment started successfully. Returns the `pipelineExecutionId`.
*   **400 Bad Request**: Invalid JSON body.
*   **500 Internal Server Error**: Failure to update secret or create repository.

---

## DELETE /deployment

Triggers the removal of an existing website deployment.

### Request Body
**Content-Type:** `application/json`

| Field | Type | Required | Description |
| :--- | :--- | :--- | :--- |
| `name` | string | Yes | The identifier of the website to delete. |
| `githubRepositoryName` | string | Yes | The name of the GitHub repository to delete. |
| `subdomain` | string | Yes | The subdomain of the site. |

**Example:**
```json
{
  "name": "project-alpha",
  "githubRepositoryName": "project-alpha-repo",
  "subdomain": "alpha"
}
```

### Behavior
1.  **Config Update:** Removes the website configuration from the `Infrastructure Config` secret.
2.  **Repo Deletion:** Deletes the GitHub repository `organization/project-alpha-repo`.
3.  **Stack Destruction:** Immediately attempts to destroy the specific CloudFormation stack associated with this website (e.g., `blueprint-project-alpha-website-stack`).

### Response
*   **200 OK**: Deployment deleted successfully.
*   **404 Not Found**: The specified deployment was not found in the configuration.
*   **500 Internal Server Error**: Failure to delete repository or destroy stack.
