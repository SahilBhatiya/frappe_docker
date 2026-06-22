BRAND_NAME = "Adarsh Motor Stores"
LOGO_URL = "/files/adarsh-motor-stores-logo.svg"


def boot_session(bootinfo):
	for app in bootinfo.get("app_data", []):
		if app.get("app_name") == "erpnext":
			app["app_title"] = BRAND_NAME
			app["app_logo_url"] = LOGO_URL

