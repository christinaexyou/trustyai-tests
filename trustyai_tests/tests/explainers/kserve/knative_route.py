from ocp_resources.resource import NamespacedResource

class Route(NamespacedResource):
    """
    KNative Route Object.
    """
    api_group:str = "serving.knative.dev/v1"

    def __init__(
        self,
        name=None,
        client=None,
        service=None,
        teardown=True,
        yaml_file=None,
        delete_timeout=None,
        **kwargs,
    ):
        super().__init__(
            **kwargs
        )

    def to_dict(self) -> None:
        super().to_dict()


    def host(self):
        """
        returns hostname that is exposing the service
        """
        return self.instance.spec.status.address.url