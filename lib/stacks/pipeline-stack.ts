import * as cdk from "aws-cdk-lib";
import * as secretsmanager from "aws-cdk-lib/aws-secretsmanager";
import BaseDeploymentConstruct from "../constructs/base-deployment-construct";

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

    new BaseDeploymentConstruct(this, "BaseDeployment", {
      pipelineName: props.pipelineName,
      githubRepoOwner: props.githubRepoOwner,
      githubRepoName: props.githubRepoName,
      codeConnectionArn: props.codeConnectionArn,
      envVariablesSecret: envVariablesSecret,
      branch: props.branch,
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
