from app.web_framework import route_node as node
from test.framework.base_unit_test_case import BaseUnitTestCase


class TestRouteNode(BaseUnitTestCase):

    def get_nested_route_tree(self):
        root_route = \
            node.RouteNode(r'/', _ExampleHandler).add_children([
                node.RouteNode(r'widget', _ExampleHandler, 'widgets').add_children([
                    node.RouteNode(r'(\d+)', _ExampleHandler, 'widget').add_children([
                        node.RouteNode(r'start', _ExampleHandler),
                        node.RouteNode(r'end', _ExampleHandler)
                    ])
                ])
            ])
        return root_route

    def test_nested_route_should_generate_multipart_regex(self):
        root_route = self.get_nested_route_tree()
        inner_route = root_route.children[0].children[0].children[0]
        self.assertEqual('/widget/(\d+)/start/?', inner_route.regex(), 'Generated regex does not match expectation.')

    def test_nested_route_should_generate_multipart_template(self):
        root_route = self.get_nested_route_tree()
        inner_route = root_route.children[0].children[0].children[0]
        self.assertEqual('/widget/[widget_id]/start', inner_route.route_template(),
                         'Generated route template does not match expectation.')

    def test_ancestors_should_return_parents_recursively(self):
        root_route = self.get_nested_route_tree()
        inner_route = root_route.children[0].children[0].children[0]
        ancestors = inner_route.ancestors()
        ancestor_names = [ancestor.name() for ancestor in ancestors]
        self.assertEqual(['[widget_id]', 'widget', '/'], ancestor_names,
                         'The list of ancestors returned does not match the list of recursive parents.')

    def test_descendants_should_return_all_children_recursively(self):
        root_route = self.get_nested_route_tree()
        descendants = root_route.descendants()
        descendant_names = [descendant.name() for descendant in descendants]
        self.assertEqual(['widget', '[widget_id]', 'start', 'end'], descendant_names,
                         'Descendants did not return the list of all children recursively')


class _ExampleHandler(object):
    def get(self, widget_id):
        pass
