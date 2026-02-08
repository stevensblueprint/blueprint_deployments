import * as lambda from "aws-cdk-lib/aws-lambda";
import * as path from "path";
import * as secretsmanager from "aws-cdk-lib/aws-secretsmanager";
import * as iam from "aws-cdk-lib/aws-iam";
import * as events from "aws-cdk-lib/aws-events";
import * as targets from "aws-cdk-lib/aws-events-targets";
import { Construct } from "constructs";

export interface DeploymentNotifyConstructProps {
  region: string;
  account: string;
  codePath: string;
  githubOauthToken: secretsmanager.ISecret;
  envVariablesSecret: secretsmanager.ISecret;
}

export default class DeploymentNotifyConstruct extends Construct {
  constructor(
    scope: Construct,
    id: string,
    props: DeploymentNotifyConstructProps,
  ) {
    super(scope, id);
    const githubUpdaterLambda = new lambda.Function(
      this,
      "GitHubUpdaterLambda",
      {
        runtime: lambda.Runtime.PYTHON_3_11,
        handler: "main.handler",
        description: "Lambda function to update GitHub status after deployment",
        code: lambda.Code.fromAsset(path.resolve(props.codePath), {
          bundling: {
            image: lambda.Runtime.PYTHON_3_11.bundlingImage,
            command: [
              "bash",
              "-c",
              [
                "set -euo pipefail",
                "pip install -r requirements.txt --no-cache-dir --platform manylinux2014_x86_64 --only-binary=:all: -t /asset-output",
                "cp -au *.py requirements.txt /asset-output",
                "find /asset-output -name '__pycache__' -prune -exec rm -rf {} +",
                "find /asset-output -name '*.pyc' -delete",
                "find /asset-output -type d \\( -name 'tests' -o -name 'test' \\) -prune -exec rm -rf {} + || true",
              ].join(" && "),
            ],
          },
        }),
        environment: {
          GITHUB_OAUTH_TOKEN_ARN: props.githubOauthToken.secretArn,
          DEPLOYMENT_SECRET_ARN: props.envVariablesSecret.secretArn,
        },
      },
    );

    props.githubOauthToken.grantRead(githubUpdaterLambda);
    props.envVariablesSecret.grantRead(githubUpdaterLambda);

    githubUpdaterLambda.addToRolePolicy(
      new iam.PolicyStatement({
        actions: [
          "cloudformation:DescribeStacks",
          "cloudformation:DescribeStackResources",
        ],
        resources: ["*"],
      }),
    );

    new events.Rule(this, "CloudFormationSuccessRule", {
      eventPattern: {
        source: ["aws.cloudformation"],
        detailType: ["CloudFormation Stack Status Change"],
        detail: {
          "status-details": {
            status: ["CREATE_COMPLETE", "UPDATE_COMPLETE"],
          },
          "stack-id": [
            {
              prefix: `arn:aws:cloudformation:${props.region}:${props.account}:stack/blueprint-`,
            },
          ],
        },
      },
      targets: [new targets.LambdaFunction(githubUpdaterLambda)],
    });
  }
}
