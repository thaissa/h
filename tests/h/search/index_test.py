import logging
from unittest import mock

import elasticsearch
import elasticsearch_dsl
import pytest
from h_matchers import Any

import h.search.index


@pytest.mark.usefixtures("annotations")
class TestIndex:
    def test_annotation_ids_are_used_as_elasticsearch_ids(
        self, es_client, factories, index_annotations
    ):
        annotation = factories.Annotation.build()

        index_annotations(annotation)

        result = es_client.conn.get(
            index=es_client.index, doc_type=es_client.mapping_type, id=annotation.id
        )
        assert result["_id"] == annotation.id

    def test_it_indexes_presented_annotation(
        self,
        factories,
        get_indexed_ann,
        index_annotations,
        pyramid_request,
        AnnotationSearchIndexPresenter,
    ):
        annotation = factories.Annotation.build()
        presenter = AnnotationSearchIndexPresenter.return_value
        presenter.asdict.return_value = {
            "id": annotation.id,
            "some_other_field": "a_value",
        }

        index_annotations(annotation)
        indexed_ann = get_indexed_ann(annotation.id)

        AnnotationSearchIndexPresenter.assert_called_once_with(
            annotation, pyramid_request
        )
        assert indexed_ann == presenter.asdict.return_value

    def test_it_notifies(
        self,
        AnnotationTransformEvent,
        factories,
        pyramid_request,
        notify,
        index_annotations,
        search,
    ):
        annotation = factories.Annotation.build(userid="acct:someone@example.com")

        index_annotations(annotation)

        event = AnnotationTransformEvent.return_value

        AnnotationTransformEvent.assert_called_once_with(
            pyramid_request, annotation, Any()
        )
        notify.assert_called_once_with(event)

    @pytest.fixture
    def annotations(self, factories, index_annotations):
        """
        Add some annotations to Elasticsearch as "noise".

        These are annotations that we *don't* expect to show up in search
        results. We want some noise in the search index to make sure that the
        test search queries are only returning the expected annotations and
        not, for example, simply returning *all* annotations.

        """
        index_annotations(
            factories.Annotation.build(),
            factories.Annotation.build(),
            factories.Annotation.build(),
        )


class TestDelete:
    def test_annotation_is_marked_deleted(
        self, es_client, factories, get_indexed_ann, index_annotations
    ):
        annotation = factories.Annotation.build(id="test_annotation_id")

        index_annotations(annotation)

        assert "deleted" not in get_indexed_ann(annotation.id)

        h.search.index.delete(es_client, annotation.id)
        assert get_indexed_ann(annotation.id).get("deleted") is True


class TestBatchIndexer:
    def test_it_indexes_all_annotations(
        self, batch_indexer, factories, get_indexed_ann
    ):
        annotations = factories.Annotation.create_batch(3)
        ids = [a.id for a in annotations]

        batch_indexer.index()

        for _id in ids:
            assert get_indexed_ann(_id) is not None

    def test_it_indexes_specific_annotations(
        self, batch_indexer, factories, get_indexed_ann
    ):
        annotations = factories.Annotation.create_batch(5)
        ids = [a.id for a in annotations]
        ids_to_index = ids[:3]
        ids_not_to_index = ids[3:]

        batch_indexer.index(ids_to_index)

        for _id in ids_to_index:
            assert get_indexed_ann(_id) is not None

        for _id in ids_not_to_index:
            with pytest.raises(elasticsearch.exceptions.NotFoundError):
                get_indexed_ann(_id)

    def test_it_does_not_index_deleted_annotations(
        self, batch_indexer, factories, get_indexed_ann
    ):
        ann = factories.Annotation()
        # create deleted annotations
        ann_del = factories.Annotation(deleted=True)

        batch_indexer.index()

        assert get_indexed_ann(ann.id) is not None

        with pytest.raises(elasticsearch.exceptions.NotFoundError):
            get_indexed_ann(ann_del.id)

    def test_it_notifies(
        self,
        AnnotationSearchIndexPresenter,
        AnnotationTransformEvent,
        batch_indexer,
        factories,
        pyramid_request,
        notify,
    ):
        annotations = factories.Annotation.create_batch(3)

        batch_indexer.index()

        event = AnnotationTransformEvent.return_value

        for annotation in annotations:
            AnnotationTransformEvent.assert_has_calls(
                [
                    mock.call(
                        pyramid_request,
                        annotation,
                        AnnotationSearchIndexPresenter.return_value.asdict.return_value,
                    )
                ]
            )
            notify.assert_has_calls([mock.call(event)])

    def test_it_logs_indexing_status(self, caplog, batch_indexer, factories):
        num_annotations = 10
        window_size = 3
        num_index_records = 0
        annotations = factories.Annotation.create_batch(num_annotations)
        ids = [a.id for a in annotations]

        with caplog.at_level(logging.INFO):
            batch_indexer.index(ids, window_size)

        for record in caplog.records:
            if record.filename == "index.py":
                num_index_records = num_index_records + 1
                assert "indexed 0k annotations, rate=" in record.msg
        assert num_index_records == num_annotations // window_size

    def test_it_correctly_indexes_fields_for_bulk_actions(
        self, batch_indexer, es_client, factories, get_indexed_ann
    ):
        annotations = factories.Annotation.create_batch(2, groupid="group_a")

        batch_indexer.index()

        for ann in annotations:
            result = get_indexed_ann(ann.id)
            assert result.get("group") == ann.groupid
            assert result.get("authority") == ann.authority
            assert result.get("user") == ann.userid
            assert result.get("uri") == ann.target_uri

    def test_it_returns_errored_annotation_ids(self, batch_indexer, factories):
        annotations = factories.Annotation.create_batch(3)
        expected_errored_ids = {annotations[0].id, annotations[2].id}

        elasticsearch.helpers.streaming_bulk = mock.Mock()
        elasticsearch.helpers.streaming_bulk.return_value = [
            (False, {"index": {"error": "some error", "_id": annotations[0].id}}),
            (True, {}),
            (False, {"index": {"error": "some error", "_id": annotations[2].id}}),
        ]

        errored = batch_indexer.index()

        assert errored == expected_errored_ids

    def test_it_does_not_error_if_annotations_already_indexed(
        self, db_session, es_client, factories, pyramid_request
    ):
        annotations = factories.Annotation.create_batch(3)
        expected_errored_ids = {annotations[1].id}

        elasticsearch.helpers.streaming_bulk = mock.Mock()
        elasticsearch.helpers.streaming_bulk.return_value = [
            (True, {}),
            (False, {"create": {"error": "some error", "_id": annotations[1].id}}),
            (
                False,
                {
                    "create": {
                        "error": "document already exists",
                        "_id": annotations[2].id,
                    }
                },
            ),
        ]

        errored = h.search.index.BatchIndexer(
            db_session, es_client, pyramid_request, es_client.index, "create"
        ).index()

        assert errored == expected_errored_ids


@pytest.fixture
def batch_indexer(db_session, es_client, pyramid_request, moderation_service):
    return h.search.index.BatchIndexer(
        db_session, es_client, pyramid_request, es_client.index
    )


@pytest.fixture
def AnnotationTransformEvent(patch):
    return patch("h.search.index.AnnotationTransformEvent")


@pytest.fixture
def AnnotationSearchIndexPresenter(patch):
    class_ = patch("h.search.index.presenters.AnnotationSearchIndexPresenter")
    class_.return_value.asdict.return_value = {"test": "val"}
    return class_


@pytest.fixture
def search(es_client, request):
    return elasticsearch_dsl.Search(using=es_client.conn, index=es_client.index)


@pytest.fixture
def get_indexed_ann(es_client):
    def _get(annotation_id):
        """
        Return the annotation with the given ID from Elasticsearch.

        Raises if the annotation is not found.
        """
        return es_client.conn.get(
            index=es_client.index, doc_type=es_client.mapping_type, id=annotation_id
        )["_source"]

    return _get
