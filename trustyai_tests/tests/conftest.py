from typing import Any, Generator, Optional

import pytest
import yaml
from kubernetes.dynamic import DynamicClient
from kubernetes.dynamic.exceptions import ConflictError
from ocp_resources.configmap import ConfigMap
from ocp_resources.namespace import Namespace
from ocp_resources.resource import get_client
from ocp_resources.role_binding import RoleBinding
from ocp_resources.service_account import ServiceAccount
from ocp_resources.trustyai_service import TrustyAIService

from trustyai_tests.tests.constants import (
    TRUSTYAI_SERVICE,
    MINIO_DATA_CONNECTION_NAME,
    ODH_OPERATOR,
)
from trustyai_tests.tests.minio import MinioSecret, MinioPod, MinioService
from trustyai_tests.tests.utils import is_odh_or_rhoai


def pytest_addoption(parser):
    parser.addoption(
        "--use-modelmesh-image", action="store_true", default=False, help="Include modelMeshImage in the ConfigMap"
    )


@pytest.fixture(scope="session")
def use_modelmesh_image(request):
    return request.config.getoption("--use-modelmesh-image")


@pytest.fixture(scope="session")
def client() -> DynamicClient:
    yield get_client()


@pytest.fixture(autouse=True, scope="session")
def modelmesh_configmap(use_modelmesh_image) -> Optional[ConfigMap]:
    operator = is_odh_or_rhoai()
    namespace = Namespace(
        name="opendatahub" if operator == ODH_OPERATOR else "redhat-ods-applications", ensure_exists=True
    )

    config_data = {
        "podsPerRuntime": 1,
    }

    if use_modelmesh_image:
        config_data["modelMeshImage"] = {"name": "quay.io/opendatahub/modelmesh", "tag": "fast"}

    with ConfigMap(
        name="model-serving-config",
        namespace=namespace.name,
        data={"config.yaml": yaml.dump(config_data)},
    ) as cm:
        yield cm


@pytest.fixture(scope="class")
def model_namespace(client: DynamicClient) -> Namespace:
    with Namespace(
        client=client,
        name="test-namespace",
        label={"modelmesh-enabled": "true"},
        delete_timeout=600,
    ) as ns:
        ns.wait_for_status(status=Namespace.Status.ACTIVE, timeout=120)
        user_name = "test-user"
        service_account = ServiceAccount(name=user_name, namespace=ns.name)
        service_account.deploy()
        role_binding = RoleBinding(
            name="test-user-view",
            namespace=ns.name,
            subjects_kind="ServiceAccount",
            subjects_name=user_name,
            role_ref_kind="ClusterRole",
            role_ref_name="view",
        )
        role_binding.deploy()
        yield ns


@pytest.fixture(scope="class")
def modelmesh_serviceaccount(client: DynamicClient, model_namespace: Namespace) -> Any:
    with ServiceAccount(client=client, name="modelmesh-serving-sa", namespace=model_namespace.name):
        yield


@pytest.fixture(scope="session")
def cluster_monitoring_config(client: DynamicClient) -> ConfigMap:
    config_yaml = yaml.dump({"enableUserWorkload": "true"})
    name = "cluster-monitoring-config"
    namespace = "openshift-monitoring"
    try:
        with ConfigMap(
            name=name,
            namespace=namespace,
            data={"config.yaml": config_yaml},
        ) as cm:
            yield cm
    except ConflictError:
        yield ConfigMap(name=name, namespace=namespace)


@pytest.fixture(scope="session")
def user_workload_monitoring_config(client: DynamicClient) -> ConfigMap:
    config_yaml = yaml.dump({"prometheus": {"logLevel": "debug", "retention": "15d"}})
    name = "user-workload-monitoring-config"
    namespace = "openshift-user-workload-monitoring"
    try:
        with ConfigMap(
            name=name,
            namespace=namespace,
            data={"config.yaml": config_yaml},
        ) as cm:
            yield cm
    except ConflictError:
        yield ConfigMap(name=name, namespace=namespace)


@pytest.fixture(scope="class")
def trustyai_service(
    client: DynamicClient,
    model_namespace: Namespace,
    modelmesh_serviceaccount: Any,
    cluster_monitoring_config: ConfigMap,
    user_workload_monitoring_config: ConfigMap,
) -> TrustyAIService:
    with TrustyAIService(
        client=client,
        name=TRUSTYAI_SERVICE,
        namespace=model_namespace.name,
        storage={"format": "PVC", "folder": "/inputs", "size": "1Gi"},
        data={"filename": "data.csv", "format": "CSV"},
        metrics={"schedule": "5s"},
    ) as trusty:
        yield trusty


@pytest.fixture(scope="class")
def minio_service(client: DynamicClient, model_namespace: Namespace) -> Generator[MinioService, Any, None]:
    with MinioService(
        name="minio",
        port=9000,
        target_port=9000,
        namespace=model_namespace.name,
        client=client,
    ) as ms:
        yield ms


@pytest.fixture(scope="class")
def minio_pod(client: DynamicClient, model_namespace: Namespace) -> Generator[MinioPod, Any, None]:
    with MinioPod(
        client=client,
        name="minio",
        namespace=model_namespace.name,
        image="quay.io/trustyai/modelmesh-minio-examples@"
        "sha256:e8360ec33837b347c76d2ea45cd4fea0b40209f77520181b15e534b101b1f323",
    ) as mp:
        yield mp


@pytest.fixture(scope="class")
def minio_secret(client: DynamicClient, model_namespace: Namespace) -> Generator[MinioSecret, Any, None]:
    with MinioSecret(
        client=client,
        name=MINIO_DATA_CONNECTION_NAME,
        namespace=model_namespace.name,
        # Dummy AWS values
        aws_access_key_id="VEhFQUNDRVNTS0VZ",
        aws_default_region="dXMtc291dGg=",
        aws_s3_bucket="bW9kZWxtZXNoLWV4YW1wbGUtbW9kZWxz",
        aws_s3_endpoint="aHR0cDovL21pbmlvOjkwMDA=",
        aws_secret_access_key="VEhFU0VDUkVUS0VZ",
    ) as ms:
        yield ms


@pytest.fixture(scope="class")
def minio_data_connection(
    minio_service: MinioService, minio_pod: MinioPod, minio_secret: MinioSecret
) -> Generator[MinioSecret, Any, None]:
    yield minio_secret
