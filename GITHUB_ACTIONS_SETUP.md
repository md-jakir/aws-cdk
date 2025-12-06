# GitHub Actions CI/CD Setup Guide

## Overview
This CI/CD pipeline automates deployment of your ECS stack to dev, stag, and prod environments based on branch.

## Branch to Environment Mapping
- `develop` → **dev** environment
- `staging` → **stag** environment  
- `main` → **prod** environment

## Prerequisites

### 1. AWS IAM Role Setup
Create an IAM role for GitHub Actions in your AWS account:

```bash
# Create the GitHub Actions role
aws iam create-role \
  --role-name GitHubActionsRole \
  --assume-role-policy-document '{
    "Version": "2012-10-17",
    "Statement": [
      {
        "Effect": "Allow",
        "Principal": {
          "Federated": "arn:aws:iam::212945523191:oidc-provider/token.actions.githubusercontent.com"
        },
        "Action": "sts:AssumeRoleWithWebIdentity",
        "Condition": {
          "StringEquals": {
            "token.actions.githubusercontent.com:aud": "sts.amazonaws.com"
          },
          "StringLike": {
            "token.actions.githubusercontent.com:sub": "repo:md-jakir/aws-cdk:*"
          }
        }
      }
    ]
  }'

# Attach necessary policies
aws iam attach-role-policy \
  --role-name GitHubActionsRole \
  --policy-arn arn:aws:iam::aws:policy/AdministratorAccess
```

### 2. GitHub Repository Secrets
Add these secrets to your GitHub repository (Settings > Secrets and variables > Actions):

```
AWS_ACCOUNT_ID=212945523191
SLACK_WEBHOOK_URL=https://hooks.slack.com/services/YOUR/WEBHOOK/URL (optional)
```

### 3. GitHub Environment Protection Rules (Optional but Recommended)
Go to Settings > Environments and create:

**Prod Environment:**
- Require approval before deployment
- Add reviewers (team leads)
- Restrict to `main` branch

**Stag Environment:**
- Restrict to `staging` branch

**Dev Environment:**
- Restrict to `develop` branch

## Workflows

### 1. `deploy.yml` - Main Deployment Pipeline
**Triggers:** Push to `main`, `staging`, `develop` branches

**Jobs:**
1. **determine-environment** - Maps branch to environment
2. **validate** - Validates CDK syntax and generates CloudFormation
3. **test** - Runs unit tests
4. **deploy** - Deploys to AWS (only on push, not PR)
5. **notify** - Sends deployment status

### 2. `preview.yml` - Pull Request Preview
**Triggers:** PR on `main` or `staging` branches

**Features:**
- Shows CloudFormation resources
- Comments on PR with changes
- Allows team review before merge

### 3. `quality.yml` - Code Quality & Security
**Triggers:** Push and PR on any branch

**Checks:**
- Python linting (Black, Flake8, Pylint)
- Security scanning (Bandit, Safety)
- Config validation

## Usage

### Deploy to Dev
```bash
git checkout develop
git push origin develop  # Automatically deploys to dev
```

### Deploy to Staging
```bash
git checkout staging
git push origin staging  # Automatically deploys to stag
```

### Deploy to Production
```bash
git checkout main
git push origin main  # Requires approval if environment protection is enabled
```

### Preview Changes (Before Merging)
```bash
git checkout -b feature/my-change
# Make changes
git push origin feature/my-change
# Create PR to main/staging
# GitHub Actions will comment with preview
```

## Monitoring

### View Workflow Runs
1. Go to your GitHub repository
2. Click **Actions** tab
3. Click on workflow name (Deploy to ECS, Preview, etc.)
4. View individual runs

### Deployment Artifacts
After deployment, check **Artifacts** section for:
- CloudFormation templates (`cdk-templates-{env}`)
- Stack outputs (`stack-outputs-{env}`)

## Troubleshooting

### Workflow Fails at AWS Credentials
**Issue:** `Unable to assume role`
**Solution:** 
- Verify IAM role ARN matches AWS account ID
- Check GitHub repository secrets are set correctly
- Ensure OIDC provider is configured

### CDK Synth Fails
**Issue:** `cdk synth error`
**Solution:**
- Run locally first: `cdk synth -c environment=dev`
- Check Python requirements.txt is installed
- Verify config.json has all required environments

### Deployment Timeout
**Issue:** Workflow takes too long
**Solution:**
- Check AWS account has enough capacity
- Verify VPC/security group settings
- Review CloudWatch logs for stack creation errors

## Security Best Practices

✅ **Implemented:**
- OIDC federated identity (no long-lived credentials)
- Environment-based approval gates (for prod)
- Minimal IAM permissions per environment
- Code quality scanning

✅ **Additional Recommendations:**
- Enable branch protection rules
- Require PR reviews before merge
- Set up Slack notifications for failures
- Rotate AWS credentials monthly

## Cost Optimization

**GitHub Actions:**
- Free tier includes 2000 minutes/month for private repos
- These workflows use ~10 minutes per deployment

**AWS:**
- Use dev environment for frequent testing
- Prod deployment only on main branch
- Monitor CloudWatch costs

## Next Steps

1. Push code to GitHub
2. Create feature branches and PRs
3. Monitor Actions tab for workflow runs
4. Review artifacts and logs
5. Merge to deploy

## Support

For issues:
1. Check workflow logs in GitHub Actions
2. Review CloudFormation events in AWS Console
3. Run `cdk deploy` locally for debugging
