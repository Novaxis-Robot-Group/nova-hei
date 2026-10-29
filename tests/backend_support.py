"""测试使用真实装配入口，机器人内部断言显式访问 robot。"""

from unittest.mock import patch


def backend_class():
    from nova_hei.app.deployments.factory import create_backend
    from nova_hei.app.deployments.settings import load_backend
    return lambda base_url, model_url: create_backend(load_backend(), base_url=base_url, model_url=model_url)


def patch_tools(tools):
    return patch('nova_hei.app.agent.api.deployment.create_tools', lambda *args, **kwargs: tools)
