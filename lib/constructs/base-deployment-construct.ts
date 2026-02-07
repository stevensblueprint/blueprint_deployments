import * as codepipeline from "aws-cdk-lib/aws-codepipeline";
import * as codepipeline_actions from "aws-cdk-lib/aws-codepipeline-actions";
import * as codebuild from "aws-cdk-lib/aws-codebuild";
import * as secretsmanager from "aws-cdk-lib/aws-secretsmanager";
import * as iam from "aws-cdk-lib/aws-iam";
import { Construct } from "constructs";

export interface BaseDeploymentConstructProps {
  pipelineName: string;
  githubRepoOwner: string;
  githubRepoName: string;
  codeConnectionArn: string;
  envVariablesSecret: secretsmanager.ISecret;
  branch?: string;
}

export default class BaseDeploymentConstruct extends Construct {
  protected readonly buildProject: codebuild.PipelineProject;
  public readonly pipeline: codepipeline.Pipeline;
  constructor(
    scope: Construct,
    id: string,
    props: BaseDeploymentConstructProps,
  ) {
    super(scope, id);
    const sourceArtifact = new codepipeline.Artifact();
    const cloudAssemblyArtifact = new codepipeline.Artifact();

    const githubSourceAction =
      new codepipeline_actions.CodeStarConnectionsSourceAction({
        actionName: "GitHub_Source",
        owner: props.githubRepoOwner,
        repo: props.githubRepoName,
        branch: props.branch ?? "main",
        connectionArn: props.codeConnectionArn,
        output: sourceArtifact,
      });

    this.buildProject = new codebuild.PipelineProject(this, "BuildProject", {
      buildSpec: codebuild.BuildSpec.fromObject({
        version: "0.2",
        env: {
          "secrets-manager": {
            ENV_VARS_SECRET_ARN: props.envVariablesSecret.secretArn,
          },
        },
        phases: {
          install: {
            "runtime-versions": {
              nodejs: "latest",
            },
            commands: ["npm i -g aws-cdk@latest", "cdk --version", "npm ci"],
          },
          pre_build: {
            commands: [
              'echo "Unpacking JSON secrets into environment variables..."',
              'echo "$ENV_VARS_SECRET_ARN" | jq -r \'to_entries[] | "export " + .key + "=" + (.value | if type == "string" then @json else (tojson | @json) end)\' > /tmp/env_vars.sh',
              "cat /tmp/env_vars.sh",
              ". /tmp/env_vars.sh",
              'echo "Environment variables loaded successfully"',
            ],
          },
          build: {
            commands: ["echo Building...", "cdk synth"],
          },
        },
        artifacts: {
          "base-directory": "cdk.out",
          files: ["**/*"],
        },
      }),
      environment: {
        buildImage: codebuild.LinuxBuildImage.STANDARD_7_0,
      },
    });

    const codeBuildAction = new codepipeline_actions.CodeBuildAction({
      actionName: "Synth",
      project: this.buildProject,
      input: sourceArtifact,
      outputs: [cloudAssemblyArtifact],
    });

    const deployProject = new codebuild.PipelineProject(this, "DeployProject", {
      buildSpec: codebuild.BuildSpec.fromObject({
        version: "0.2",
        env: {
          "secrets-manager": {
            ENV_VARS_SECRET_ARN: props.envVariablesSecret.secretArn,
          },
        },
        phases: {
          install: {
            "runtime-versions": {
              nodejs: "latest",
            },
            commands: ["npm i -g aws-cdk@latest", "cdk --version"],
          },
          pre_build: {
            commands: [
              'echo "Unpacking JSON secrets into environment variables..."',
              'echo "$ENV_VARS_SECRET_ARN" | jq -r \'to_entries[] | "export " + .key + "=" + (.value | if type == "string" then @json else (tojson | @json) end)\' > /tmp/env_vars.sh',
              "cat /tmp/env_vars.sh",
              ". /tmp/env_vars.sh",
              'echo "Environment variables loaded successfully"',
            ],
          },
          build: {
            commands: [
              "echo Deploying all stacks...",
              "ls -la",
              "cdk deploy '*-website-stack' --app . --require-approval never",
            ],
          },
        },
      }),
      environment: {
        buildImage: codebuild.LinuxBuildImage.STANDARD_7_0,
      },
    });

    deployProject.addToRolePolicy(
      new iam.PolicyStatement({
        actions: ["ssm:GetParameter", "ssm:AssumeRole"],
        resources: ["*"],
      }),
    );

    deployProject.addToRolePolicy(
      new iam.PolicyStatement({
        actions: ["sts:AssumeRole"],
        resources: [
          `arn:aws:iam::*:role/cdk-*-deploy-role-*`,
          `arn:aws:iam::*:role/cdk-*-file-publishing-role-*`,
          `arn:aws:iam::*:role/cdk-*-lookup-role-*`,
        ],
      }),
    );

    deployProject.addToRolePolicy(
      new iam.PolicyStatement({
        actions: ["cloudformation:*"],
        resources: ["*"],
      }),
    );

    props.envVariablesSecret.grantRead(this.buildProject);
    props.envVariablesSecret.grantRead(deployProject);

    const deployAction = new codepipeline_actions.CodeBuildAction({
      actionName: "Deploy_All",
      project: deployProject,
      input: cloudAssemblyArtifact,
    });

    this.pipeline = new codepipeline.Pipeline(this, "Pipeline", {
      pipelineName: props.pipelineName,
      stages: [
        {
          stageName: "Source",
          actions: [githubSourceAction],
        },
        {
          stageName: "Build",
          actions: [codeBuildAction],
        },
        {
          stageName: "Deploy",
          actions: [deployAction],
        },
      ],
    });
  }
}
