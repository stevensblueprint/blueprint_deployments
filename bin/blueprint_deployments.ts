#!/usr/bin/env node
import * as cdk from "aws-cdk-lib/core";
import { config } from "./config";
import { PipelineStack } from "../lib/stacks/pipeline-stack";

const app = new cdk.App();
new PipelineStack(app, "blueprint-deployments-pipeline-stack", {
  env: {
    account: process.env.CDK_DEFAULT_ACCOUNT,
    region: process.env.CDK_DEFAULT_REGION,
  },
  description: "CDK Pipeline stack to manage blueprint deployments",
  pipelineName: config.pipelineName,
  githubRepoOwner: config.githubRepoOwner,
  githubRepoName: config.githubRepoName,
  codeConnectionArn: config.codeConnectionArn,
});
