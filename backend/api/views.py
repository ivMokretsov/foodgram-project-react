from django.db.models import Sum
from django.http import Http404, HttpResponse
from django.shortcuts import get_object_or_404
from djoser.views import TokenCreateView, UserViewSet
from django_filters.rest_framework.backends import DjangoFilterBackend
from rest_framework.decorators import action
from rest_framework.permissions import SAFE_METHODS, IsAuthenticated
from rest_framework.response import Response
from rest_framework.status import (
    HTTP_200_OK,
    HTTP_201_CREATED,
    HTTP_204_NO_CONTENT,
    HTTP_400_BAD_REQUEST,
    HTTP_404_NOT_FOUND
)
from rest_framework.viewsets import ModelViewSet, GenericViewSet

from .constants import ERRORS_KEY
from .mixins import ListRetriveViewSet
from .pagination import LimitPageNumberPagination
from .permissions import IsAuthorOrAdminOrReadOnly
from .filters import IngredientSearchFilter, RecipeFilter
from .serializers import (
    IngredientSerializer,
    RecipeReadSerializer,
    RecipeWriteSerializer,
    TagSerializer,
    RecipeShortReadSerializer,
    SubscriptionSerializer
)
from recipes.models import Favorite, Ingredient, Recipe, Tag
from users.models import ShoppingCart, Subscribe, User


FAVORITE_ALREADY_EXISTS = 'Вы уже подписаны!'
FAVORITE_DONT_EXIST = 'Подписки не существует!'


class TagViewSet(ListRetriveViewSet):
    serializer_class = TagSerializer
    queryset = Tag.objects.all()
    http_method_names = ('get',)


class IngredientViewSet(ListRetriveViewSet):
    serializer_class = IngredientSerializer
    filter_backends = (DjangoFilterBackend,)
    filterset_class = IngredientSearchFilter
    queryset = Ingredient.objects.all()
    http_method_names = ('get',)


class RecipeViewSet(ModelViewSet):
    pagination_class = LimitPageNumberPagination
    permission_classes = (IsAuthorOrAdminOrReadOnly,)
    filter_backends = (DjangoFilterBackend,)
    filterset_class = RecipeFilter
    queryset = Recipe.objects.all()
    http_method_names = ('get', 'post', 'put', 'patch', 'delete',)

    def get_serializer_class(self):
        if self.request.method in SAFE_METHODS:
            return RecipeReadSerializer
        return RecipeWriteSerializer

    def perform_create(self, serializer):
        serializer.save(author=self.request.user)

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        self.perform_create(serializer)
        serializer = RecipeReadSerializer(
            instance=serializer.instance,
            context={'request': self.request}
        )
        headers = self.get_success_headers(serializer.data)
        return Response(
            serializer.data, status=HTTP_201_CREATED, headers=headers
        )

    def update(self, request, *args, **kwargs):
        partial = kwargs.pop('partial', False)
        instance = self.get_object()
        serializer = self.get_serializer(
            instance, data=request.data, partial=partial
        )
        serializer.is_valid(raise_exception=True)
        self.perform_update(serializer)
        serializer = RecipeReadSerializer(
            instance=serializer.instance,
            context={'request': self.request},
        )
        return Response(
            serializer.data, status=HTTP_200_OK
        )

    def add_to_favorite(self, request, recipe):
        favorite = Favorite.objects.filter(user=request.user, recipe=recipe)
        if favorite.exists():
            return Response(
                {ERRORS_KEY: FAVORITE_ALREADY_EXISTS},
                status=HTTP_400_BAD_REQUEST,
            )
        Favorite.objects.create(user=request.user, recipe=recipe)

        serializer = RecipeShortReadSerializer(recipe)
        return Response(
            serializer.data,
            status=HTTP_201_CREATED,
        )

    def delete_from_favorite(self, request, recipe):
        favorite = Favorite.objects.filter(user=request.user, recipe=recipe)
        if not favorite.exists():
            return Response(
                {ERRORS_KEY: FAVORITE_DONT_EXIST},
                status=HTTP_400_BAD_REQUEST,
            )
        favorite.delete()
        return Response(status=HTTP_204_NO_CONTENT)

    @action(
        methods=('get', 'delete',),
        detail=True,
        permission_classes=(IsAuthenticated,)
    )
    def favorite(self, request, pk=None):
        recipe = get_object_or_404(Recipe, pk=pk)
        if request.method == 'GET':
            return self.add_to_favorite(request, recipe)
        return self.delete_from_favorite(request, recipe)


FILE_NAME = 'shopping_cart.txt'

SUBSCRIBE_CANNOT_CREATE_TO_YOURSELF = 'Нельзя подписаться на самого себя!'
SUBSCRIBE_CANNOT_CREATE_TWICE = 'Нельзя подписаться дважды!'
SUBSCRIBE_CANNOT_DELETE = (
    'Нельзя отписаться от данного пользователя,'
    ' если вы не подписаны на него!'
)

USER_BLOCKED = 'Данный аккаунт временно заблокирован!'
USER_NOT_FOUND = 'Пользователь не найден!'

SHOPPING_CART_DOES_NOT_EXISTS = 'Список покупок не существует!'
SHOPPING_CART_RECIPE_CANNOT_ADDED_TWICE = 'Рецепт уже добавлен!'
SHOPPING_CART_RECIPE_CANNOT_DELETE = (
    'Нельзя удалить рецепт из списка покупок, которого нет'
    ' в списке покупок!'
)


class TokenCreateWithCheckBlockStatusView(TokenCreateView):
    def _action(self, serializer):
        if serializer.user.is_blocked:
            return Response(
                {ERRORS_KEY: USER_BLOCKED},
                status=HTTP_400_BAD_REQUEST,
            )
        return super()._action(serializer)


class UserSubscribeViewSet(UserViewSet):
    pagination_class = LimitPageNumberPagination
    lookup_url_kwarg = 'user_id'

    def get_subscribtion_serializer(self, *args, **kwargs):
        kwargs.setdefault('context', self.get_serializer_context())
        return SubscriptionSerializer(*args, **kwargs)

    @action(detail=False, permission_classes=(IsAuthenticated,))
    def subscriptions(self, request):
        self.get_serializer
        queryset = User.objects.filter(subscribing__user=request.user)
        page = self.paginate_queryset(queryset)
        if page is not None:
            serializer = self.get_subscribtion_serializer(page, many=True)
            return self.get_paginated_response(serializer.data)
        serializer = self.get_subscribtion_serializer(queryset, many=True)
        return Response(serializer.data, status=HTTP_200_OK)

    def create_subscribe(self, request, author):
        if request.user == author:
            return Response(
                {ERRORS_KEY: SUBSCRIBE_CANNOT_CREATE_TO_YOURSELF},
                status=HTTP_400_BAD_REQUEST,
            )
        subscribe = Subscribe.objects.filter(
                user=request.user,
                author=author
        )
        if subscribe.exists():
            return Response(
                {ERRORS_KEY: SUBSCRIBE_CANNOT_CREATE_TWICE},
                status=HTTP_400_BAD_REQUEST,
            )
        subscribe = Subscribe.objects.create(
            user=request.user,
            author=author,
        )
        serializer = self.get_subscribtion_serializer(subscribe.author)
        return Response(serializer.data, status=HTTP_201_CREATED)

    def delete_subscribe(self, request, author):
        try:
            Subscribe.objects.get(user=request.user, author=author).delete()
        except Subscribe.DoesNotExist:
            return Response(
                {ERRORS_KEY: SUBSCRIBE_CANNOT_DELETE},
                status=HTTP_400_BAD_REQUEST,
            )
        return Response(
            status=HTTP_204_NO_CONTENT
        )

    @action(
        methods=('get', 'delete',),
        detail=True,
        permission_classes=(IsAuthenticated,)
    )
    def subscribe(self, request, user_id=None):
        try:
            author = get_object_or_404(User, pk=user_id)
        except Http404:
            return Response(
                {'detail': USER_NOT_FOUND},
                status=HTTP_404_NOT_FOUND,
            )
        if request.method == 'GET':
            return self.create_subscribe(request, author)
        return self.delete_subscribe(request, author)


class ShoppingCartViewSet(GenericViewSet):
    NAME = 'ingredients__ingredient__name'
    MEASUREMENT_UNIT = 'ingredients__ingredient__measurement_unit'
    permission_classes = (IsAuthenticated,)
    serializer_class = RecipeShortReadSerializer
    queryset = ShoppingCart.objects.all()
    http_method_names = ('get', 'delete',)

    def generate_shopping_cart_data(self, request):
        recipes = (
            request.user.shopping_cart.recipes.prefetch_related('ingredients')
        )
        return (
            recipes.order_by(self.NAME)
            .values(self.NAME, self.MEASUREMENT_UNIT)
            .annotate(total=Sum('ingredients__amount'))
        )

    def generate_ingredients_content(self, ingredients):
        content = ''
        for ingredient in ingredients:
            content += (
                f'{ingredient[self.NAME]}'
                f' ({ingredient[self.MEASUREMENT_UNIT]})'
                f' — {ingredient["total"]}\r\n'
            )
        return content

    @action(detail=False)
    def download_shopping_cart(self, request):
        ingredients = self.generate_shopping_cart_data(request)
        if not ingredients.exists():
            return Response(
                {ERRORS_KEY: SHOPPING_CART_DOES_NOT_EXISTS},
                status=HTTP_400_BAD_REQUEST
            )
        content = self.generate_ingredients_content(ingredients)
        response = HttpResponse(
            content, content_type='text/plain,charset=utf8'
        )
        response['Content-Disposition'] = f'attachment; filename={FILE_NAME}'
        return response

    def add_to_shopping_cart(self, recipe, shopping_cart):
        if shopping_cart.recipes.filter(pk__in=(recipe.pk,)).exists():
            return Response(
                {ERRORS_KEY: SHOPPING_CART_RECIPE_CANNOT_ADDED_TWICE},
                status=HTTP_400_BAD_REQUEST,
            )
        shopping_cart.recipes.add(recipe)
        serializer = self.get_serializer(recipe)
        return Response(
            serializer.data,
            status=HTTP_201_CREATED,
        )

    def remove_from_shopping_cart(self, recipe, shopping_cart):
        if not shopping_cart.recipes.filter(pk__in=(recipe.pk,)).exists():
            return Response(
                {ERRORS_KEY: SHOPPING_CART_RECIPE_CANNOT_DELETE},
                status=HTTP_400_BAD_REQUEST,
            )
        shopping_cart.recipes.remove(recipe)
        return Response(
            status=HTTP_204_NO_CONTENT,
        )

    @action(methods=('get', 'delete',), detail=True)
    def shopping_cart(self, request, pk=None):
        recipe = get_object_or_404(Recipe, pk=pk)
        shopping_cart = (
            ShoppingCart.objects.get_or_create(user=request.user)[0]
        )
        if request.method == 'GET':
            return self.add_to_shopping_cart(request, recipe, shopping_cart)
        return self.remove_from_shopping_cart(request, recipe, shopping_cart)
