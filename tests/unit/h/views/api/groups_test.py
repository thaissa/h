from unittest.mock import PropertyMock, call, create_autospec, sentinel

import pytest
from pyramid.httpexceptions import HTTPConflict

import h.views.api.groups as views
from h.models import User
from h.schemas.base import ValidationError
from h.traversal import GroupContext
from h.views.api.exceptions import PayloadError


class TestGroups:
    def test_it_without_request_params(
        self, pyramid_request, group_list_service, GroupsJSONPresenter
    ):
        response = views.groups(pyramid_request)

        group_list_service.request_groups.assert_called_once_with(
            user=pyramid_request.user,
            authority=None,
            document_uri=None,
        )
        GroupsJSONPresenter.assert_called_once_with(
            group_list_service.request_groups.return_value, pyramid_request
        )
        GroupsJSONPresenter.return_value.asdicts.assert_called_once_with(expand=[])
        assert response == GroupsJSONPresenter.return_value.asdicts.return_value

    def test_it_with_request_params(
        self, pyramid_request, group_list_service, GroupsJSONPresenter
    ):
        pyramid_request.GET.add("expand", sentinel.expand_1)
        pyramid_request.GET.add("expand", sentinel.expand_2)
        pyramid_request.params["authority"] = sentinel.authority
        pyramid_request.params["document_uri"] = sentinel.document_uri

        views.groups(pyramid_request)

        group_list_service.request_groups.assert_called_once_with(
            user=pyramid_request.user,
            authority=sentinel.authority,
            document_uri=sentinel.document_uri,
        )
        GroupsJSONPresenter.return_value.asdicts.assert_called_once_with(
            expand=[sentinel.expand_1, sentinel.expand_2]
        )


@pytest.mark.usefixtures("group_service", "group_create_service")
class TestCreate:
    def test_it_validates_the_request(self, pyramid_request, CreateGroupAPISchema):
        views.create(pyramid_request)

        CreateGroupAPISchema.assert_called_once_with(
            request=pyramid_request,
            default_authority=pyramid_request.default_authority,
            group_authority=sentinel.effective_authority,
        )
        CreateGroupAPISchema.return_value.validate.assert_called_once_with(
            pyramid_request.json_body
        )

    def test_it_when_request_json_body_isnt_valid_json(self, pyramid_request, mocker):
        value_error = ValueError()
        mocker.patch.object(
            type(pyramid_request),
            "json_body",
            PropertyMock(side_effect=value_error),
            create=True,
        )

        with pytest.raises(PayloadError) as exc_info:
            views.create(pyramid_request)

        assert exc_info.value.__cause__ == value_error

    def test_it_when_request_json_body_is_invalid(
        self, pyramid_request, CreateGroupAPISchema
    ):
        CreateGroupAPISchema.return_value.validate.side_effect = ValidationError

        with pytest.raises(ValidationError):
            views.create(pyramid_request)

    @pytest.mark.parametrize(
        "appstruct,group_create_service_method_call",
        [
            (
                {
                    "name": sentinel.name,
                    "description": sentinel.description,
                    "type": "private",
                    "pre_moderated": False,
                },
                call.create_private_group(
                    name=sentinel.name,
                    userid=sentinel.userid,
                    description=sentinel.description,
                    groupid=None,
                    pre_moderated=False,
                ),
            ),
            (
                {"name": sentinel.name},
                call.create_private_group(
                    name=sentinel.name,
                    userid=sentinel.userid,
                    description=None,
                    groupid=None,
                    pre_moderated=False,
                ),
            ),
        ],
    )
    def test_create_private_group(
        self,
        pyramid_request,
        CreateGroupAPISchema,
        group_create_service,
        appstruct,
        group_create_service_method_call,
        assert_it_returns_group_as_json,
    ):
        CreateGroupAPISchema.return_value.validate.return_value = appstruct

        response = views.create(pyramid_request)

        assert group_create_service.method_calls == [group_create_service_method_call]
        assert_it_returns_group_as_json(
            response,
            group=group_create_service.create_private_group.return_value,
        )

    @pytest.mark.parametrize(
        "appstruct,group_create_service_method_call",
        [
            (
                {
                    "name": sentinel.name,
                    "description": sentinel.description,
                    "type": "restricted",
                    "pre_moderated": True,
                },
                call.create_restricted_group(
                    name=sentinel.name,
                    userid=sentinel.userid,
                    scopes=[],
                    description=sentinel.description,
                    groupid=None,
                    pre_moderated=True,
                ),
            ),
            (
                {"name": sentinel.name, "type": "restricted"},
                call.create_restricted_group(
                    name=sentinel.name,
                    userid=sentinel.userid,
                    scopes=[],
                    description=None,
                    groupid=None,
                    pre_moderated=False,
                ),
            ),
        ],
    )
    def test_create_restricted_group(
        self,
        pyramid_request,
        CreateGroupAPISchema,
        group_create_service,
        assert_it_returns_group_as_json,
        appstruct,
        group_create_service_method_call,
    ):
        CreateGroupAPISchema.return_value.validate.return_value = appstruct

        response = views.create(pyramid_request)

        assert group_create_service.method_calls == [group_create_service_method_call]
        assert_it_returns_group_as_json(
            response, group=group_create_service.create_restricted_group.return_value
        )

    @pytest.mark.parametrize(
        "appstruct,group_create_service_method_call",
        [
            (
                {
                    "name": sentinel.name,
                    "description": sentinel.description,
                    "type": "open",
                    "pre_moderated": True,
                },
                call.create_open_group(
                    name=sentinel.name,
                    userid=sentinel.userid,
                    scopes=[],
                    description=sentinel.description,
                    groupid=None,
                    pre_moderated=True,
                ),
            ),
            (
                {"name": sentinel.name, "type": "open"},
                call.create_open_group(
                    name=sentinel.name,
                    userid=sentinel.userid,
                    scopes=[],
                    description=None,
                    groupid=None,
                    pre_moderated=False,
                ),
            ),
        ],
    )
    def test_create_open_group(
        self,
        pyramid_request,
        CreateGroupAPISchema,
        group_create_service,
        assert_it_returns_group_as_json,
        appstruct,
        group_create_service_method_call,
    ):
        CreateGroupAPISchema.return_value.validate.return_value = appstruct

        response = views.create(pyramid_request)

        assert group_create_service.method_calls == [group_create_service_method_call]
        assert_it_returns_group_as_json(
            response, group=group_create_service.create_open_group.return_value
        )

    def test_it_with_groupid_request_param(
        self, pyramid_request, CreateGroupAPISchema, group_service, group_create_service
    ):
        CreateGroupAPISchema.return_value.validate.return_value["groupid"] = (
            sentinel.groupid
        )

        views.create(pyramid_request)

        group_service.fetch.assert_called_once_with(pubid_or_groupid=sentinel.groupid)
        assert (
            group_create_service.create_private_group.call_args[1]["groupid"]
            == sentinel.groupid
        )

    def test_it_with_duplicate_groupid(
        self, pyramid_request, group_service, CreateGroupAPISchema
    ):
        CreateGroupAPISchema.return_value.validate.return_value["groupid"] = (
            sentinel.groupid
        )
        group_service.fetch.return_value = sentinel.duplicate_group

        with pytest.raises(
            HTTPConflict, match="group with groupid 'sentinel.groupid' already exists"
        ):
            views.create(pyramid_request)

    @pytest.fixture
    def pyramid_request(self, pyramid_request):
        pyramid_request.json_body = sentinel.json_body
        return pyramid_request


class TestRead:
    def test_it(self, context, pyramid_request, assert_it_returns_group_as_json):
        pyramid_request.GET.add("expand", sentinel.expand_1)
        pyramid_request.GET.add("expand", sentinel.expand_2)

        response = views.read(context, pyramid_request)

        assert_it_returns_group_as_json(
            response, context.group, expand=[sentinel.expand_1, sentinel.expand_2]
        )

    def test_it_with_no_expand_request_param(
        self, context, pyramid_request, assert_it_returns_group_as_json
    ):
        response = views.read(context, pyramid_request)

        assert_it_returns_group_as_json(response, context.group, expand=[])


@pytest.mark.usefixtures("group_service", "group_update_service")
class TestUpdate:
    def test_it_validates_the_request(
        self, context, pyramid_request, UpdateGroupAPISchema
    ):
        views.update(context, pyramid_request)

        UpdateGroupAPISchema.assert_called_once_with(
            request=pyramid_request,
            default_authority=pyramid_request.default_authority,
            group_authority=sentinel.effective_authority,
        )
        UpdateGroupAPISchema.return_value.validate.assert_called_once_with(
            pyramid_request.json_body
        )

    def test_it_when_request_json_body_isnt_valid_json(
        self, context, pyramid_request, mocker
    ):
        value_error = ValueError()
        mocker.patch.object(
            type(pyramid_request),
            "json_body",
            PropertyMock(side_effect=value_error),
            create=True,
        )

        with pytest.raises(PayloadError) as exc_info:
            views.update(context, pyramid_request)

        assert exc_info.value.__cause__ == value_error

    def test_it_when_request_json_body_is_invalid(
        self, context, pyramid_request, UpdateGroupAPISchema
    ):
        UpdateGroupAPISchema.return_value.validate.side_effect = ValidationError

        with pytest.raises(ValidationError):
            views.update(context, pyramid_request)

    @pytest.mark.parametrize(
        "appstruct,group_update_service_method_call",
        [
            ({}, call.update(sentinel.group)),
            ({"name": sentinel.name}, call.update(sentinel.group, name=sentinel.name)),
            (
                {"description": sentinel.description},
                call.update(sentinel.group, description=sentinel.description),
            ),
            ({"type": "private"}, call.update(sentinel.group, type="private")),
            (
                {
                    "name": sentinel.name,
                    "description": sentinel.description,
                    "type": "private",
                },
                call.update(
                    sentinel.group,
                    name=sentinel.name,
                    description=sentinel.description,
                    type="private",
                ),
            ),
            ({"pre_moderated": True}, call.update(sentinel.group, pre_moderated=True)),
        ],
    )
    def test_update(
        self,
        context,
        pyramid_request,
        UpdateGroupAPISchema,
        group_update_service,
        assert_it_returns_group_as_json,
        appstruct,
        group_update_service_method_call,
    ):
        UpdateGroupAPISchema.return_value.validate.return_value = appstruct

        response = views.update(context, pyramid_request)

        assert group_update_service.method_calls == [group_update_service_method_call]
        assert_it_returns_group_as_json(
            response, group=group_update_service.update.return_value
        )

    def test_it_with_groupid_request_param(
        self,
        context,
        pyramid_request,
        group_service,
        group_update_service,
        UpdateGroupAPISchema,
    ):
        UpdateGroupAPISchema.return_value.validate.return_value["groupid"] = (
            sentinel.groupid
        )
        group_service.fetch.return_value = context.group

        views.update(context, pyramid_request)

        group_service.fetch.assert_called_once_with(pubid_or_groupid=sentinel.groupid)
        assert group_update_service.update.call_args[1]["groupid"] == sentinel.groupid

    def test_it_with_duplicate_groupid(
        self,
        context,
        pyramid_request,
        group_service,
        group_update_service,
        UpdateGroupAPISchema,
    ):
        UpdateGroupAPISchema.return_value.validate.return_value["groupid"] = (
            sentinel.groupid
        )
        group_service.fetch.return_value = sentinel.duplicate_group

        with pytest.raises(
            HTTPConflict, match="group with groupid 'sentinel.groupid' already exists"
        ):
            views.update(context, pyramid_request)

        group_update_service.update.assert_not_called()

    @pytest.fixture
    def pyramid_request(self, pyramid_request):
        pyramid_request.json_body = sentinel.json_body
        return pyramid_request


@pytest.fixture
def assert_it_returns_group_as_json(GroupJSONPresenter, pyramid_request):
    def assert_it_returns_group_as_json(
        response, group, expand=("organization", "scopes")
    ):
        expand = list(expand)  # Turn the default value into a list.
        GroupJSONPresenter.assert_called_once_with(group, pyramid_request)
        GroupJSONPresenter.return_value.asdict.assert_called_once_with(expand=expand)
        assert response == GroupJSONPresenter.return_value.asdict.return_value

    return assert_it_returns_group_as_json


@pytest.fixture
def pyramid_request(pyramid_request):
    pyramid_request.effective_authority = sentinel.effective_authority
    pyramid_request.user = create_autospec(
        User, instance=True, spec_set=True, userid=sentinel.userid
    )
    return pyramid_request


@pytest.fixture
def group_service(group_service):
    group_service.fetch.return_value = None
    return group_service


@pytest.fixture(autouse=True)
def GroupJSONPresenter(mocker):
    return mocker.patch(
        "h.views.api.groups.GroupJSONPresenter", autospec=True, spec_set=True
    )


@pytest.fixture(autouse=True)
def GroupsJSONPresenter(mocker):
    return mocker.patch(
        "h.views.api.groups.GroupsJSONPresenter", autospec=True, spec_set=True
    )


@pytest.fixture(autouse=True)
def CreateGroupAPISchema(mocker):
    CreateGroupAPISchema = mocker.patch(
        "h.views.api.groups.CreateGroupAPISchema", autospec=True, spec_set=True
    )
    CreateGroupAPISchema.return_value.validate.return_value = {"name": sentinel.name}
    return CreateGroupAPISchema


@pytest.fixture(autouse=True)
def UpdateGroupAPISchema(mocker):
    UpdateGroupAPISchema = mocker.patch(
        "h.views.api.groups.UpdateGroupAPISchema", autospec=True, spec_set=True
    )
    UpdateGroupAPISchema.return_value.validate.return_value = {}
    return UpdateGroupAPISchema


@pytest.fixture
def context():
    return create_autospec(
        GroupContext, instance=True, spec_set=True, group=sentinel.group
    )
