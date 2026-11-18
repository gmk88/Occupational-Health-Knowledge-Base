from locust import HttpUser, between, task


class KnowledgeBaseUser(HttpUser):
    wait_time = between(1, 2)

    @task(6)
    def search(self):
        self.client.post(
            "/api/v1/search",
            json={"query": "苯系物接触限值", "mode": "hybrid", "top_k": 5},
        )

    @task(1)
    def health(self):
        self.client.get("/api/v1/health")
