from subprocess import check_output
import requests
import logging
import yaml
import os

# https://docs.gitlab.com/ce/api/projects.html#upload-a-file
# https://docs.gitlab.com/ee/api/releases/#create-a-release
# https://docs.gitlab.com/ee/ci/variables/#syntax-of-environment-variables-in-job-scripts

yamlBlacklist = [
    "image",
    "variables",
    "services",
    "before_script",
]

cienvs = [
    "CI_SERVER_VERSION_MAJOR",
    "CI_SERVER_VERSION_MINOR",
    "CI_SERVER_VERSION_PATCH",
    "CI_RUNNER_DESCRIPTION",
    "CI_PROJECT_NAMESPACE",
    "CI_REGISTRY_PASSWORD",
    "CI_COMMIT_SHORT_SHA",
    "CI_COMMIT_REF_NAME",
    "CI_SERVER_REVISION",
    "CI_REPOSITORY_URL",
    "CI_REGISTRY_IMAGE",
    "CI_SERVER_VERSION",
    "GITLAB_USER_EMAIL",
    "CI_JOB_TRIGGERED",
    "CI_REGISTRY_USER",
    "CI_PIPELINE_IID",
    "CI_PAGES_DOMAIN",
    "CI_PROJECT_NAME",
    "CI_PROJECT_PATH",
    "CI_PIPELINE_ID",
    "CI_PROJECT_DIR",
    "CI_PROJECT_URL",
    "CI_RUNNER_TAGS",
    "CI_SERVER_NAME",
    "GITLAB_USER_ID",
    "CI_COMMIT_SHA",
    "CI_COMMIT_TAG",
    "CI_JOB_MANUAL",
    "CI_PROJECT_ID",
    "CI_JOB_STAGE",
    "CI_JOB_TOKEN",
    "CI_PAGES_URL",
    "CI_RUNNER_ID",
    "CI_JOB_NAME",
    "CI_REGISTRY",
    "CI_JOB_ID",
    "CI_SERVER",
]

class gitlab_api(object):
    def __init__(self, url, projectId, apiKey):
        # init session and api key
        self.s = requests.session()
        self.s.headers.update({"PRIVATE-TOKEN": apiKey})

        # project id we are currently working on
        self.projectId = projectId

        # set our url e.g. https://gitlab.com/api/v4
        self.api_url = url
        if self.api_url[-1:] == "/":
            self.api_url = self.api_url[:-1]

        # all our endpoints
        self.api_upload = "{}/projects/{}/uploads".format(self.api_url, self.projectId)
        self.api_releases = "{}/projects/{}/releases".format(self.api_url, self.projectId)

        # git-chglog command
        self.gitchglog_config = os.getenv("GITCHGLOG_CONFIG", "/opt/chglog/config.yml")
        self.cmd_gitchglog = "git-chglog --config {}".format(self.gitchglog_config)

    def fileExists(self, path):
        return os.path.isfile(path)
    def dirExists(self, path):
        return os.path.isdir(path)
    def filesDir(self, path):
        if not self.dirExists(path):
            logging.error("directory does not exists")
            return False
        files = []
        for r, d, f in os.walk(path):
            for file in f:
                files.append(os.path.join(r, file))
        return files

    def uploadFile(self, path):
        if not self.fileExists(path):
            logging.error("files does not exists")
            return False
        
        files = {"file": open(path, 'rb')}
        r = self.s.post(self.api_upload, files=files)
        
        return r.json()

    def uploadDir(self, path):
        if not self.dirExists(path):
            logging.error("dir does not exists")
            return False

        files = self.filesDir(path)

        fileRes = []
        for file in files:
            fileUpload = self.uploadFile(file)
            fileRes.append(fileUpload)

        return fileRes

    def parseYaml(self, path):
        if not self.fileExists(path):
            logging.error("yaml does not exists")
            return False

        f = open(path, "r")
        data = f.read()
        f.close()

        release = yaml.safe_load(data)

        # make sure we have the required stuff
        if "name" not in release:
            logging.error("conf: need name for our release!")
            return False
        elif "tag_name" not in release:
            logging.error("conf: need tag_name for our release!")
            return False
        elif "description" not in release:
            logging.error("conf: need description for our release!")
            return False

        # fix our environment variables
        for key in release:
            value = release[key]

            if type(value) is not str:
                continue

            for cienv in cienvs:
                value = value.replace("$"+cienv, os.getenv(cienv, "ERRORNOTSET"))
                value = value.replace("${"+cienv+"}", os.getenv(cienv, "ERRORNOTSET"))
            release[key] = value

        name        = release["name"]
        tag_name    = release["tag_name"]
        description = release["description"]
        assets_dir = False
        if "assets_dir" in release:
            assets_dir = release["assets_dir"]
        changelog = False
        if "changelog" in release:
            changelog = release["changelog"]

        print(name,tag_name,description, assets_dir, changelog)
        return self.makeRelease(name, tag_name, description, uploads=assets_dir, changelog=changelog)

    def makeRelease(self, name, tag_name, description, ref = None, assets = None, changelog = False, uploads = False):
        # check if our description is a file, and read if so
        if self.fileExists(description):
            f = open(description, "r")
            description = f.read()

        # if changelog is needed, then lets do that!
        if changelog:
            # specifies which version we want a changelog for
            outChangelog = check_output(self.cmd_gitchglog+" "+changelog, shell=True).strip()
            description += "\n\n"
            description += "# Changelog\n"
            description += outChangelog.decode("utf8")

        # check for any uploads, and upload if nescceary
        uploadsFiles = []
        if uploads:
            if self.fileExists(uploads):
                uploadsFiles.append(self.uploadFile(uploads))
            elif self.dirExists(uploads):
                uploadsFiles = self.uploadDir(uploads)
            else:
                logging.error("unknown format for uploads or no such dir/file")
                return False

        # if any files were uploaded, then please do mark them as assets
        if len(uploadsFiles) > 0:
            description += "\n\n"
            description += "# Assets\n"
            for file in uploadsFiles:
                print(file)
                description += "- "+file["markdown"]+"\n"

        data = {
                "name": name,
                "tag_name": tag_name,
                "description": description,
        }

        if ref:
            data["ref"] = ref
        if assets:
            data["assets"] = []
            for asset in assets:
                data["assets"].append(asset)

        r = self.s.post(self.api_releases, data=data)

        # if everything went well, return true!
        return r

url = os.getenv("GITLAB_API_URL", "https://gitlab.com/api/v4/")
projectId = os.getenv("CI_PROJECT_ID", None)
apiKey = os.getenv("GITLAB_API_KEY", None)

x = gitlab_api(url, projectId, apiKey)
out = x.parseYaml(".gitlab-ci-release.yml")

if out == False:
    print("Failed to make release")
    exit(1)
elif out.status_code != 201:
    print("Failed to make release")
    print(out.text)
    exit(1)
else:
    print("Made release!")
    exit(0)
