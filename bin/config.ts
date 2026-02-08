import { z } from "zod";
import * as dotenv from "dotenv";

dotenv.config();

const arnRegex = /^arn:aws:[a-z0-9-]+:[a-z0-9-]*:\d{12}:.+$/i;

const SCHEMA = z
  .object({
    PIPELINE_NAME: z.string().min(1, "PIPELINE_NAME is required"),
    GITHUB_REPO_NAME: z.string().min(1, "GITHUB_REPO_NAME is required"),
    GITHUB_REPO_OWNER: z.string().min(1, "GITHUB_REPO_OWNER is required"),
    CODE_CONNECTION_ARN: z
      .string()
      .regex(arnRegex, "CODE_CONNECTION_ARN must be a valid AWS ARN"),
  })
  .transform((env) => ({
    pipelineName: env.PIPELINE_NAME,
    githubRepoName: env.GITHUB_REPO_NAME,
    githubRepoOwner: env.GITHUB_REPO_OWNER,
    codeConnectionArn: env.CODE_CONNECTION_ARN,
  }));

export const config = SCHEMA.parse(process.env);
