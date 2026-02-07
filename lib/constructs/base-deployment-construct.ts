import * as codepipeline from "aws-cdk-lib/aws-codepipeline";
import * as codepipeline_actions from "aws-cdk-lib/aws-codepipeline-actions";
import * as codebuild from "aws-cdk-lib/aws-codebuild";
import * as secretsmanager from "aws-cdk-lib/aws-secretsmanager";
import * as cdk from "aws-cdk-lib";
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
            commands: ["npm ci"],
          },
          pre_build: {
            commands: [
              'echo "Unpacking JSON secrets into environment variables..."',
              'eval "$(echo "$ENV_VARS_SECRET_ARN" | jq -r \'to_entries | .[] | "export \\(.key)=\\\"\\(.value)\\\"\"\' )"',
            ],
          },
          build: {
            commands: ["echo Building...", "npx cdk synth"],
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
          },
          pre_build: {
            commands: [
              'echo "Unpacking JSON secrets into environment variables..."',
              'eval "$(echo "$ENV_VARS_SECRET_ARN" | jq -r \'to_entries | .[] | "export \\(.key)=\\\"\\(.value)\\\"\"\' )"',
            ],
          },
          build: {
            commands: [
              "echo Deploying all stacks...",
              "npx cdk deploy --all --require-approval never",
            ],
          },
        },
      }),
      environment: {
        buildImage: codebuild.LinuxBuildImage.STANDARD_7_0,
      },
    });

    props.envVariablesSecret.grantRead(this.buildProject);
    props.envVariablesSecret.grantRead(deployProject);

    const deployAction = new codepipeline_actions.CodeBuildAction({
      actionName: "Deploy_All",
      project: deployProject,
      input: cloudAssemblyArtifact,
    });

    new codepipeline.Pipeline(this, "Pipeline", {
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
