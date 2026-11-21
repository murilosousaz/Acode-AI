"""MongoDocumentRepository: monta o pipeline do $vectorSearch (sem Mongo real)."""

from src.infrastructure.database.mongodb.mongo_document_repo import MongoDocumentRepository


class FakeCursor:
    def __init__(self, docs):
        self.docs = docs

    async def to_list(self, length):
        return self.docs[:length]


class FakeCollection:
    name = "document_chunks"

    def __init__(self, docs=None, error=None):
        self.docs = docs or []
        self.error = error
        self.pipeline = None

    def aggregate(self, pipeline):
        self.pipeline = pipeline
        if self.error:
            raise self.error
        return FakeCursor(self.docs)


def make_repo(collection):
    repo = MongoDocumentRepository.__new__(MongoDocumentRepository)  # evita precisar de um db real
    repo.collection = collection
    repo.vector_index_name = "vector_index"
    return repo


async def test_subject_filter_uses_explicit_eq():
    collection = FakeCollection()
    await make_repo(collection).search_similar_chunks([0.1, 0.2], top_k=4, subject="Fisica")
    stage = collection.pipeline[0]["$vectorSearch"]
    assert stage["filter"] == {"metadata.subject": {"$eq": "Fisica"}}
    assert stage["limit"] == 4 and stage["numCandidates"] >= 100 and stage["index"] == "vector_index"


async def test_no_subject_means_no_filter():
    collection = FakeCollection()
    await make_repo(collection).search_similar_chunks([0.1], top_k=4)
    assert "filter" not in collection.pipeline[0]["$vectorSearch"]


async def test_results_carry_score_in_metadata_and_no_embedding():
    docs = [{"_id": "abc", "content": "texto", "metadata": {"title": "T", "subject": "Fisica"}, "score": 0.87}]
    [found] = await make_repo(FakeCollection(docs)).search_similar_chunks([0.1], top_k=4)
    assert found.content == "texto" and found.chunk_id == "abc" and found.embedding == []
    assert found.metadata == {"title": "T", "subject": "Fisica", "score": 0.87}


async def test_database_errors_propagate():
    import pytest

    with pytest.raises(RuntimeError):
        await make_repo(FakeCollection(error=RuntimeError("index not found"))).search_similar_chunks([0.1])
