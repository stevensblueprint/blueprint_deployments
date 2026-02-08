import * as cdk from "aws-cdk-lib";
import * as secretsmanager from "aws-cdk-lib/aws-secretsmanager";
import BaseDeploymentConstruct from "../constructs/base-deployment-construct";
import ApiDeployConstruct from "../constructs/api-deploy-construct";
import DeploymentNotifyConstruct from "../constructs/deployment-notify-construct";

export interface PipelineStackProps extends cdk.StackProps {
  pipelineName: string;
  githubRepoOwner: string;
  githubRepoName: string;
  codeConnectionArn: string;
  branch?: string;
}

export class PipelineStack extends cdk.Stack {
  constructor(scope: cdk.App, id: string, props: PipelineStackProps) {
    super(scope, id, props);
    const envVariablesSecret = new secretsmanager.Secret(
      this,
      `${props.pipelineName}-EnvVariablesSecret`,
      {
        secretName: `${props.pipelineName}-env-variables`,
        description: "Secret to store environment variables for the pipeline",
      },
    );

    const baseDeployment = new BaseDeploymentConstruct(this, "BaseDeployment", {
      pipelineName: props.pipelineName,
      githubRepoOwner: props.githubRepoOwner,
      githubRepoName: props.githubRepoName,
      codeConnectionArn: props.codeConnectionArn,
      envVariablesSecret: envVariablesSecret,
      branch: props.branch,
    });

    const githubOauthTokenSecret = new secretsmanager.Secret(
      this,
      "GitHubOAuthTokenSecret",
      {
        secretName: `${props.pipelineName}-github-oauth-token`,
        description: "Secret to store GitHub OAuth token for API deployment",
      },
    );

    new ApiDeployConstruct(this, "ApiDeployment", {
      deploymentSecret: envVariablesSecret,
      pipeline: baseDeployment.pipeline,
      codePath: "lambda/deploy-api-function",
      githubOauthTokenArn: githubOauthTokenSecret,
    });

    new DeploymentNotifyConstruct(this, "DeploymentNotify", {
      codePath: "lambda/notify-deployment-function",
      githubOauthToken: githubOauthTokenSecret,
      region: this.region,
      account: this.account,
      envVariablesSecret: envVariablesSecret,
    });

    new cdk.CfnOutput(this, "PipelineName", {
      value: props.pipelineName,
    });

    new cdk.CfnOutput(this, "EnvVariablesSecretArn", {
      value: envVariablesSecret.secretArn,
    });

    new cdk.CfnOutput(this, "EnvVariablesSecretName", {
      value: envVariablesSecret.secretName,
    });
  }
}
