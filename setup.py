
if __name__ == '__main__':
    from setuptools import setup
    setup(
        name='cffibuilder',
        description='Foreign Function Interface for Python calling C code',
        version='0.1',
        packages=['cffibuilder'],
        zip_safe=False,
        license='MIT',
        install_requires=[
            'pycparser',
        ],
    )
