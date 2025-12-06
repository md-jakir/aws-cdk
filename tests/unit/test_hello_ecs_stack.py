import aws_cdk as core
import aws_cdk.assertions as assertions

from hello_ecs.hello_ecs_stack import DemoEcsStack

# example tests. To run these tests, uncomment this file along with the example
# resource in hello_ecs/hello_ecs_stack.py
def test_sqs_queue_created():
    app = core.App()
    stack = DemoEcsStack(app, "hello-ecs")
    template = assertions.Template.from_stack(stack)

#     template.has_resource_properties("AWS::SQS::Queue", {
#         "VisibilityTimeout": 300
#     })
