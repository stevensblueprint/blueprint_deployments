import * as lambda from "aws-cdk-lib/aws-lambda";
import * as apigateway from "aws-cdk-lib/aws-apigateway";
import * as secretsmanager from "aws-cdk-lib/aws-secretsmanager";
import * as path from "path";
import * as codepipeline from "aws-cdk-lib/aws-codepipeline";
import * as iam from "aws-cdk-lib/aws-iam";
import * as cdk from "aws-cdk-lib";
import { Construct } from "constructs";

export interface ApiDeployConstructProps {
  deploymentSecret: secretsmanager.ISecret;
  pipeline: codepipeline.IPipeline;
  codePath: string;
  githubOauthTokenArn: secretsmanager.ISecret;
}

export default class ApiDeployConstruct extends Construct {
  constructor(scope: Construct, id: string, props: ApiDeployConstructProps) {
    super(scope, id);
    const apiLambdaFunction = new lambda.Function(this, "ApiLambdaFunction", {
      runtime: lambda.Runtime.PYTHON_3_11,
      code: lambda.Code.fromAsset(path.resolve(props.codePath)),
      handler: "main.handler",
      description: "API lambda function to trigger deployments",
      environment: {
        DEPLOYMENT_SECRET_ARN: props.deploymentSecret.secretArn,
        PIPELINE_NAME: props.pipeline.pipelineName,
        GITHUB_OAUTH_TOKEN_ARN: props.githubOauthTokenArn.secretArn,
      },
    });

    props.deploymentSecret.grantWrite(apiLambdaFunction);
    props.deploymentSecret.grantRead(apiLambdaFunction);
    props.githubOauthTokenArn.grantRead(apiLambdaFunction);

    apiLambdaFunction.addToRolePolicy(
      new iam.PolicyStatement({
        actions: ["codepipeline:StartPipelineExecution"],
        resources: [props.pipeline.pipelineArn],
      }),
    );

    apiLambdaFunction.addToRolePolicy(
      new iam.PolicyStatement({
        actions: [
          "cloudformation:DeleteStack",
          "cloudformation:DescribeStacks",
        ],
        resources: [
          `arn:aws:cloudformation:${cdk.Stack.of(this).region}:${cdk.Stack.of(this).account}:stack/blueprint-*-website-stack/*`,
        ],
      }),
    );

    const api = new apigateway.RestApi(this, "ApiDeployGateway", {
      description: "API Gateway for deployment trigger",
    });

    const deployResource = api.root.addResource("deploy");
    const deploymentResource = api.root.addResource("deployment");

    const requestModel = new apigateway.Model(this, "DeployRequestModel", {
      restApi: api,
      contentType: "application/json",
      schema: {
        schema: apigateway.JsonSchemaVersion.DRAFT4,
        title: "DeployRequest",
        type: apigateway.JsonSchemaType.OBJECT,
        properties: {
          name: { type: apigateway.JsonSchemaType.STRING },
          subdomain: { type: apigateway.JsonSchemaType.STRING },
          githubRepositoryName: { type: apigateway.JsonSchemaType.STRING },
          githubBranchName: { type: apigateway.JsonSchemaType.STRING },
          requiresAuth: { type: apigateway.JsonSchemaType.BOOLEAN },
          includeRootDomain: { type: apigateway.JsonSchemaType.BOOLEAN },
        },
        required: [
          "name",
          "subdomain",
          "githubRepositoryName",
          "githubBranchName",
          "requiresAuth",
          "includeRootDomain",
        ],
      },
    });

    const deleteRequestModel = new apigateway.Model(
      this,
      "DeleteDeployRequestModel",
      {
        restApi: api,
        contentType: "application/json",
        schema: {
          schema: apigateway.JsonSchemaVersion.DRAFT4,
          title: "DeleteDeployRequest",
          type: apigateway.JsonSchemaType.OBJECT,
          properties: {
            name: { type: apigateway.JsonSchemaType.STRING },
            githubRepositoryName: { type: apigateway.JsonSchemaType.STRING },
            subdomain: { type: apigateway.JsonSchemaType.STRING },
          },
          required: ["name", "githubRepositoryName", "subdomain"],
        },
      },
    );

    const pollReuquestModel = new apigateway.Model(
      this,
      "PollDeployRequestModel",
      {
        restApi: api,
        contentType: "application/json",
        schema: {
          schema: apigateway.JsonSchemaVersion.DRAFT4,
          title: "PollDeployRequest",
          type: apigateway.JsonSchemaType.OBJECT,
          properties: {},
        },
      },
    );

    const requestValidator = new apigateway.RequestValidator(
      this,
      "DeployRequestValidator",
      {
        restApi: api,
        validateRequestBody: true,
      },
    );

    deployResource.addMethod(
      "POST",
      new apigateway.LambdaIntegration(apiLambdaFunction),
      {
        requestModels: { "application/json": requestModel },
        requestValidator,
      },
    );

    deploymentResource.addMethod(
      "DELETE",
      new apigateway.LambdaIntegration(apiLambdaFunction),
      {
        requestModels: { "application/json": deleteRequestModel },
        requestValidator,
      },
    );

    new cdk.CfnOutput(this, "ApiDeployUrl", {
      value: api.url,
    });

    new cdk.CfnOutput(this, "ApiDeployEndpoint", {
      value: `${api.url}deploy`,
    });

    new cdk.CfnOutput(this, "ApiDeploymentEndpoint", {
      value: `${api.url}deployment`,
    });
  }
}
