import aws_cdk as cdk
from constructs import Construct
import json
import os

import aws_cdk.aws_ecs as ecs
import aws_cdk.aws_ecs_patterns as ecsp
import aws_cdk.aws_ec2 as ec2
import aws_cdk.aws_elasticloadbalancingv2 as elbv2
import aws_cdk.aws_iam as iam
import aws_cdk.aws_logs as logs
import aws_cdk.aws_cloudwatch as cloudwatch

class DemoEcsStack(cdk.Stack):

    def __init__(self, scope: Construct, construct_id: str, taskdef_path: str = None, chatbot_frontend_taskdef_path: str = None, environment: str = "dev", config: dict = None, **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)

        # Use provided config or defaults
        if config is None:
            config = {
                "cluster_name": "keycloak_cluster",
                "lb_name": "keycloak-lb",
                "keycloak": {
                    "desired_count": 1,
                    "cpu": 256,
                    "memory": 512,
                    "max_capacity": 3,
                    "min_capacity": 1,
                    "cpu_target": 70,
                    "memory_target": 80,
                    "health_check_path": "/health/ready",
                    "log_retention_days": 7
                },
                "chatbot_frontend": {
                    "desired_count": 1,
                    "cpu": 256,
                    "memory": 512,
                    "max_capacity": 3,
                    "min_capacity": 1,
                    "cpu_target": 70,
                    "memory_target": 80,
                    "health_check_path": "/",
                    "log_retention_days": 7
                },
                "vpc": {
                    "max_azs": 2,
                    "cidr": "10.0.0.0/16"
                }
            }

        keycloak_config = config.get("keycloak", {})
        chatbot_config = config.get("chatbot_frontend", {})
        vpc_config = config.get("vpc", {})

        # Create VPC
        vpc = ec2.Vpc(self, "Vpc", max_azs=vpc_config.get("max_azs", 2), cidr=vpc_config.get("cidr", "10.0.0.0/16"))

        # Create Cluster
        cluster = ecs.Cluster(self, "Cluster", vpc=vpc, cluster_name=config.get("cluster_name", "keycloak_cluster"))

        # Create execution role for Fargate tasks
        execution_role = iam.Role(self, "ExecutionRole",
            assumed_by=iam.ServicePrincipal("ecs-tasks.amazonaws.com"),
        )
        execution_role.add_managed_policy(
            iam.ManagedPolicy.from_aws_managed_policy_name("service-role/AmazonECSTaskExecutionRolePolicy")
        )

        # Create CloudWatch Log Group for container logs
        retention_days = keycloak_config.get("log_retention_days", 7)
        retention_map = {
            7: logs.RetentionDays.ONE_WEEK,
            14: logs.RetentionDays.TWO_WEEKS,
            30: logs.RetentionDays.ONE_MONTH,
            60: logs.RetentionDays.TWO_MONTHS,
            90: logs.RetentionDays.THREE_MONTHS,
        }
        retention = retention_map.get(retention_days, logs.RetentionDays.ONE_WEEK)
        
        log_group = logs.LogGroup(self, "EcsLogGroup",
            log_group_name=f"/ecs/keycloak-{environment}",
            retention=retention,
            removal_policy=cdk.RemovalPolicy.DESTROY
        )

        # Load task definition from JSON file if provided
        if taskdef_path and os.path.exists(taskdef_path):
            with open(taskdef_path, 'r') as f:
                taskdef_json = json.load(f)
            
            # Create Fargate task definition with values from JSON
            task_definition = ecs.FargateTaskDefinition(self, "CustomTaskDef",
                memory_limit_mib=int(taskdef_json.get('memory', 512)),
                cpu=int(taskdef_json.get('cpu', 256)),
                execution_role=execution_role,
            )
            
            # Add containers from JSON containerDefinitions
            for container in taskdef_json.get('containerDefinitions', []):
                task_definition.add_container(
                    container.get('name', 'app'),
                    image=ecs.ContainerImage.from_registry(container.get('image', 'amazon/amazon-ecs-sample')),
                    memory_limit_mib=container.get('memory', 512),
                    port_mappings=[ecs.PortMapping(container_port=pm.get('containerPort', 80)) 
                                  for pm in container.get('portMappings', [{'containerPort': 80}])],
                    logging=ecs.LogDriver.aws_logs(
                        log_group=log_group,
                        stream_prefix="keycloak"
                    )
                )
        else:
            # Fallback to default task definition if no JSON file provided
            task_definition = ecs.FargateTaskDefinition(self, "TaskDef",
                memory_limit_mib=512,
                cpu=256,
                execution_role=execution_role,
            )
            task_definition.add_container("DefaultContainer",
                image=ecs.ContainerImage.from_registry("amazon/amazon-ecs-sample"),
                memory_limit_mib=512,
                port_mappings=[ecs.PortMapping(container_port=80)],
                logging=ecs.LogDriver.aws_logs(
                    log_group=log_group,
                    stream_prefix="keycloak"
                )
            )

        # Create Fargate service
        service = ecs.FargateService(self, "Service",
            cluster=cluster,
            task_definition=task_definition,
            desired_count=keycloak_config.get("desired_count", 1),
        )

        # Add Auto Scaling for the service
        scaling = service.auto_scale_task_count(
            min_capacity=keycloak_config.get("min_capacity", 1),
            max_capacity=keycloak_config.get("max_capacity", 3),
        )

        # Scale on CPU utilization
        scaling.scale_on_cpu_utilization("CpuScaling",
            target_utilization_percent=keycloak_config.get("cpu_target", 70),
        )

        # Scale on memory utilization
        scaling.scale_on_memory_utilization("MemoryScaling",
            target_utilization_percent=keycloak_config.get("memory_target", 80),
        )

        # Add Application Load Balancer
        lb = elbv2.ApplicationLoadBalancer(self, "LB", vpc=vpc, internet_facing=True, load_balancer_name=config.get("lb_name", "keycloak-lb"))
        listener = lb.add_listener("Listener", port=80)
        target_group = listener.add_targets("Target",
            port=80,
            targets=[service],
            health_check=elbv2.HealthCheck(
                path=keycloak_config.get("health_check_path", "/health/ready"),
                interval=cdk.Duration.seconds(30),
                timeout=cdk.Duration.seconds(5),
                healthy_threshold_count=2,
                unhealthy_threshold_count=3,
            )
        )

        # CloudWatch Alarms for monitoring
        # CPU Utilization Alarm
        cpu_alarm = cloudwatch.Alarm(self, "CpuAlarm",
            metric=service.metric_cpu_utilization(),
            threshold=keycloak_config.get("cpu_target", 70),
            evaluation_periods=2,
            datapoints_to_alarm=2,
            alarm_description="Alert when CPU utilization reaches threshold",
            alarm_name=f"keycloak-cpu-alarm-{environment}"
        )

        # Memory Utilization Alarm
        memory_alarm = cloudwatch.Alarm(self, "MemoryAlarm",
            metric=service.metric_memory_utilization(),
            threshold=keycloak_config.get("memory_target", 80),
            evaluation_periods=2,
            datapoints_to_alarm=2,
            alarm_description="Alert when Memory utilization reaches threshold",
            alarm_name=f"keycloak-memory-alarm-{environment}"
        )

        # Unhealthy Target Count Alarm (from target group)
        unhealthy_alarm = cloudwatch.Alarm(self, "UnhealthyTargetsAlarm",
            metric=target_group.metric_unhealthy_host_count(),
            threshold=1,
            evaluation_periods=1,
            comparison_operator=cloudwatch.ComparisonOperator.GREATER_THAN_OR_EQUAL_TO_THRESHOLD,
            alarm_description="Alert when there are unhealthy targets",
            alarm_name=f"keycloak-unhealthy-targets-alarm-{environment}"
        )

        cdk.CfnOutput(self, "LoadBalancerDNS", value=lb.load_balancer_dns_name)

        # ===== CHATBOT FRONTEND SERVICE =====
        # Create CloudWatch Log Group for chatbot-frontend
        chatbot_retention_days = chatbot_config.get("log_retention_days", 7)
        chatbot_retention = retention_map.get(chatbot_retention_days, logs.RetentionDays.ONE_WEEK)
        
        chatbot_frontend_log_group = logs.LogGroup(self, "ChatbotFrontendLogGroup",
            log_group_name=f"/ecs/chatbot-frontend-{environment}",
            retention=chatbot_retention,
            removal_policy=cdk.RemovalPolicy.DESTROY
        )

        # Load chatbot-frontend task definition from JSON
        if chatbot_frontend_taskdef_path and os.path.exists(chatbot_frontend_taskdef_path):
            with open(chatbot_frontend_taskdef_path, 'r') as f:
                chatbot_frontend_json = json.load(f)
            
            # Create Fargate task definition for chatbot-frontend
            chatbot_frontend_taskdef = ecs.FargateTaskDefinition(self, "ChatbotFrontendTaskDef",
                memory_limit_mib=chatbot_config.get("memory", 512),
                cpu=chatbot_config.get("cpu", 256),
                execution_role=execution_role,
            )
            
            # Add containers from chatbot-frontend JSON
            for container in chatbot_frontend_json.get('containerDefinitions', []):
                environment_vars = {}
                for env in container.get('environment', []):
                    environment_vars[env.get('name')] = env.get('value')
                
                chatbot_frontend_taskdef.add_container(
                    container.get('name', 'chatbot-frontend'),
                    image=ecs.ContainerImage.from_registry(container.get('image')),
                    memory_limit_mib=container.get('memory', 512),
                    port_mappings=[ecs.PortMapping(container_port=pm.get('containerPort', 3000)) 
                                  for pm in container.get('portMappings', [{'containerPort': 3000}])],
                    environment=environment_vars,
                    logging=ecs.LogDriver.aws_logs(
                        log_group=chatbot_frontend_log_group,
                        stream_prefix="chatbot-frontend"
                    )
                )

            # Create Fargate service for chatbot-frontend
            chatbot_frontend_service = ecs.FargateService(self, "ChatbotFrontendService",
                cluster=cluster,
                task_definition=chatbot_frontend_taskdef,
                desired_count=chatbot_config.get("desired_count", 1),
                service_name="chatbot-frontend"
            )

            # Add Auto Scaling for chatbot-frontend
            chatbot_frontend_scaling = chatbot_frontend_service.auto_scale_task_count(
                min_capacity=chatbot_config.get("min_capacity", 1),
                max_capacity=chatbot_config.get("max_capacity", 3),
            )

            chatbot_frontend_scaling.scale_on_cpu_utilization("ChatbotFrontendCpuScaling",
                target_utilization_percent=chatbot_config.get("cpu_target", 70),
            )

            chatbot_frontend_scaling.scale_on_memory_utilization("ChatbotFrontendMemoryScaling",
                target_utilization_percent=chatbot_config.get("memory_target", 80),
            )

            # Create target group for chatbot-frontend
            chatbot_frontend_target_group = elbv2.ApplicationTargetGroup(
                self, "ChatbotFrontendTargetGroup",
                vpc=vpc,
                port=3000,
                protocol=elbv2.ApplicationProtocol.HTTP,
                target_type=elbv2.TargetType.IP,
                target_group_name="chatbot-frontend",
                health_check=elbv2.HealthCheck(
                    path=chatbot_config.get("health_check_path", "/"),
                    protocol=elbv2.Protocol.HTTP,
                    port="3000",
                    healthy_threshold_count=2,
                    unhealthy_threshold_count=3,
                    interval=cdk.Duration.seconds(30),
                    timeout=cdk.Duration.seconds(5),
                )
            )

            # Register targets
            chatbot_frontend_target_group.add_target(chatbot_frontend_service)

            # Add listener rule for path-based routing
            listener.add_target_groups(
                "ChatbotFrontendRule",
                conditions=[elbv2.ListenerCondition.path_patterns(["/frontend", "/frontend/*"])],
                priority=100,
                target_groups=[chatbot_frontend_target_group]
            )

            # CloudWatch Alarms for chatbot-frontend
            chatbot_cpu_alarm = cloudwatch.Alarm(self, "ChatbotCpuAlarm",
                metric=chatbot_frontend_service.metric_cpu_utilization(),
                threshold=chatbot_config.get("cpu_target", 70),
                evaluation_periods=2,
                datapoints_to_alarm=2,
                alarm_description="Alert when chatbot-frontend CPU reaches threshold",
                alarm_name=f"chatbot-frontend-cpu-alarm-{environment}"
            )

            chatbot_memory_alarm = cloudwatch.Alarm(self, "ChatbotMemoryAlarm",
                metric=chatbot_frontend_service.metric_memory_utilization(),
                threshold=chatbot_config.get("memory_target", 80),
                evaluation_periods=2,
                datapoints_to_alarm=2,
                alarm_description="Alert when chatbot-frontend memory reaches threshold",
                alarm_name=f"chatbot-frontend-memory-alarm-{environment}"
            )

            chatbot_unhealthy_alarm = cloudwatch.Alarm(self, "ChatbotUnhealthyTargetsAlarm",
                metric=chatbot_frontend_target_group.metric_unhealthy_host_count(),
                threshold=1,
                evaluation_periods=1,
                comparison_operator=cloudwatch.ComparisonOperator.GREATER_THAN_OR_EQUAL_TO_THRESHOLD,
                alarm_description="Alert when chatbot-frontend has unhealthy targets",
                alarm_name=f"chatbot-frontend-unhealthy-targets-alarm-{environment}"
            )

            cdk.CfnOutput(self, "ChatbotFrontendTargetGroupArn", value=chatbot_frontend_target_group.target_group_arn)