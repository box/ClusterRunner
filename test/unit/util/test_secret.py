from genty import genty, genty_dataset
import hashlib

from test.framework.base_unit_test_case import BaseUnitTestCase
from app.util.secret import Secret


@genty
class TestSecret(BaseUnitTestCase):

    def test_get_secret_should_return_set_secret(self):
        secret = 'secret1234'
        Secret.set(secret)
        self.assertEqual(secret, Secret.get())

    @genty_dataset(None, '', 'short')
    def test_set_insecure_secrets_fails(self, insecure_secret):
        self.assertRaises(RuntimeError, Secret.set, insecure_secret)

    def test_header_generates_128_character_digest(self):
        secret = hashlib.sha512().hexdigest()
        header = Secret.header('message', secret)
        self.assertEqual(len(header[Secret.DIGEST_HEADER_KEY]), 128)

    def test_matching_digests_should_return_true(self):
        secret = 'secrettoken'
        message = 'message blah blah horse battery staple'
        Secret.set(secret)
        digest_received = Secret._get_hex_digest(message, secret)

        self.assertTrue(Secret.digest_is_valid(digest_received, message))

    def test_non_matching_digests_should_return_false(self):
        secret = 'secrettoken'
        message = 'message blah blah horse battery staple'
        Secret.set(secret)
        digest_received = Secret._get_hex_digest('not the original message', secret)

        self.assertFalse(Secret.digest_is_valid(digest_received, message))

    def test_unspecified_digest_should_return_false(self):
        secret = 'secrettoken'
        message = 'message blah blah horse battery staple'
        Secret.set(secret)
        digest_received = None

        self.assertFalse(Secret.digest_is_valid(digest_received, message))
