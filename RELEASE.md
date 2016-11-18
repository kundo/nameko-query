# Releasing a new version of nameko-query

1. Verify that tests are green (`tox`)
2. Obtain and add `.pypirc` in your home directory
3. Bump version number in `setup.py`
4. Build and upload the new release (`python setup.py bdist_wheel upload -r pypi`)
5. Tag the version (`git tag -a v0.0.x`, `git push origin v0.0.x`)
