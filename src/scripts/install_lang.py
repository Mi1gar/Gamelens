import argostranslate.package
import argostranslate.translate
import sys

def install_languages():
    print("Updating package index...")
    argostranslate.package.update_package_index()
    
    available_packages = argostranslate.package.get_available_packages()
    
    # Looking for English -> Turkish
    package_to_install = next(
        filter(
            lambda x: x.from_code == "en" and x.to_code == "tr", available_packages
        ), None
    )
    
    if package_to_install:
        print(f"Downloading and installing: {package_to_install}")
        argostranslate.package.install_from_path(package_to_install.download())
        print("Success! En->Tr installed.")
    else:
        print("Error: Could not find En->Tr package.")

if __name__ == "__main__":
    install_languages()
