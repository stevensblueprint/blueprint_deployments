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
    ```json
    {
      "message": "Pipeline execution started.",
      "pipelineExecutionId": "a1b2c3d4-5678-90ab-cdef-123456789012"
    }
    ```
*   **400 Bad Request**: Invalid JSON body.
*   **500 Internal Server Error**: Failure to update secret or create repository.

---

## GET /deployments

Lists all currently configured website deployments.

### Request Body
None.

### Response
*   **200 OK**: Returns a list of website configurations.
    ```json
    [
      {
        "name": "project-alpha",
        "subdomain": "alpha",
        "githubRepositoryName": "project-alpha-repo",
        "githubBranchName": "main",
        "requiresAuth": false,
        "includeRootDomain": false
      }
    ]
    ```
*   **500 Internal Server Error**: Failure to load configuration.

---

## GET /deployment/{executionId}

Polls the status of a specific deployment (CodePipeline execution).

### Path Parameters
| Parameter | Type | Required | Description |
| :--- | :--- | :--- | :--- |
| `executionId` | string | Yes | The ID returned by the `POST /deploy` request. |

### Response
*   **200 OK**: Returns the current status of the deployment.
    ```json
    {
      "executionId": "a1b2c3d4-5678-90ab-cdef-123456789012",
      "status": "Succeeded",
      "stages": [
        {
          "name": "Source",
          "status": "Succeeded",
          "lastUpdate": "2026-02-08T12:00:00Z"
        },
        {
          "name": "Build",
          "status": "Succeeded",
          "lastUpdate": "2026-02-08T12:05:00Z"
        },
        {
          "name": "Deploy",
          "status": "Succeeded",
          "lastUpdate": "2026-02-08T12:10:00Z"
        }
      ],
      "url": "https://alpha.example.com",
      "error": null
    }
    ```
*   **404 Not Found**: The specified execution ID was not found.
*   **500 Internal Server Error**: Failure to fetch pipeline status.

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
