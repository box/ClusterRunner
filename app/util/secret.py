import hmac


class Secret:
    DIGEST_HEADER_KEY = 'Clusterrunner-Message-Authentication-Digest'
    _secret = None

    @classmethod
    def get(cls):
        """
        :return: The secret that was set with the set(secret) method
        :rtype: str
        """
        return cls._secret

    @classmethod
    def set(cls, secret):
        """
        :param secret: The secret that will be used by the application to authenticate network requests
        :type secret: str
        """
        if not secret or len(secret) == 0:
            raise RuntimeError('Empty secret is not allowed!')
        if len(secret) < 8:
            raise RuntimeError('Secret must be at least 8 characters long!')
        cls._secret = secret

    @classmethod
    def header(cls, message, secret=None):
        """
        Produces a header which contains a digest of a message, generated using the shared secret
        :type secret: str
        :return: The header to use in authenticated network requests
        :rtype: dict
        """
        secret = secret or cls.get()
        return {cls.DIGEST_HEADER_KEY: cls._get_hex_digest(message, secret)}

    @classmethod
    def _get_hex_digest(cls, message, secret):
        """
        Create a message authentication digest, using a shared secret and the message
        :type message: str
        :type secret: str
        :return: A 64 character hex string
        :rtype: str
        """
        hmac_digester = hmac.new(secret.encode('utf-8'), message.encode('utf-8'), digestmod='sha512')
        return hmac_digester.hexdigest()

    @classmethod
    def digest_is_valid(cls, digest_received, message_received):
        """
        Check if a digested message matches the digest passed in.
        :param digest_received: The Message Authentication digest the client has passed in
        :type digest_received: str
        :param message_received: The message the client has passed in
        :type message_received: str
        :return: Whether the message digest matches the digest passed in (proving the client knows the same secret)
        :rtype: bool
        """
        digest_received = digest_received or ''
        message_digest = cls._get_hex_digest(message_received, cls.get())

        # hmac.compare_digest protects against timing attacks
        if not hmac.compare_digest(digest_received, message_digest):
            return False
        return True
