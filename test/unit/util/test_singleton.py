from test.framework.base_unit_test_case import BaseUnitTestCase
from app.util.singleton import Singleton, SingletonError


class TestSingleton(BaseUnitTestCase):

    def test_singleton_returns_same_instance_every_time(self):
        instance_a = Singleton.singleton()
        instance_b = Singleton.singleton()
        self.assertIs(instance_a, instance_b, 'Singleton.singleton() should return the same instance.')

    def test_singleton_raises_error_on_multiple_instantiations(self):
        instance_a = Singleton.singleton()

        with self.assertRaises(SingletonError, msg='Instantiating more than once should raise an error.'):
            instance_b = Singleton()

    def test_singletons_can_be_reset(self):
        instance_a = Singleton.singleton()
        Singleton.reset_singleton()
        instance_b = Singleton.singleton()

        self.assertTrue(instance_a is not instance_b,
                        'Singleton.singleton() should return a different instance after reset.')
