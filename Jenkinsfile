pipeline {

  triggers {
    githubPush()
  }

  agent none

  tools {
    nodejs 'node20'
  }

  environment {
    AWS_ECR_REGISTRY            = "324037323031.dkr.ecr.us-east-2.amazonaws.com/nws"
    BACKEND_IMAGE               = "${AWS_ECR_REGISTRY}/main-load-data"
    BACKEND_IMAGE_TAG           = "${BACKEND_IMAGE}:latest"
    BACKEND_CONTAINER_IMAGE     = "aws_ms_main_load_data"
    BACKEND_CONTAINER_IMAGE_TAG = "${BACKEND_CONTAINER_IMAGE}:latest"
    AWS_DEFAULT_REGION          = "us-east-2"
    AWS_CLUSTER                 = "api-dealerportal-cluster"
    AWS_BACKEND_SERVICE         = "main-load-data-service"
    JENKINS_HOOK                = "main-load-data-repository-hook"
  }

  stages {

    stage('1. Checkout & Stash') {
      agent any
      steps {
        checkout scm
        stash name: 'source', includes: '**'
      }
    }

    stage('2. Verify agent groups') {
      agent { label 'docker' }
      steps {
        sh 'echo "Users: $(id -un)"'
        sh 'echo "Groups: $(id -Gn)"'
      }
    }

    stage('3. Smoke Test Docker') {
      agent { label 'docker' }
      steps {
        echo "🔍 Testing Docker from this agent in EC2..."
        sh 'docker version'
        sh 'docker info'
        sh 'docker-compose version'
      }
    }

    stage('4. Login to ECR') {
      agent { label 'docker' }
      steps {
        withCredentials([[
          $class: 'AmazonWebServicesCredentialsBinding',
          credentialsId: 'aws-ecr-creds'
        ]]) {
          sh '''
            docker run --rm \
              -e AWS_ACCESS_KEY_ID=$AWS_ACCESS_KEY_ID \
              -e AWS_SECRET_ACCESS_KEY=$AWS_SECRET_ACCESS_KEY \
              amazon/aws-cli ecr get-login-password --region $AWS_DEFAULT_REGION \
            | docker login --username AWS --password-stdin $AWS_ECR_REGISTRY
          '''
        }
      }
    }

    stage('5. Prune Docker') {
      agent { label 'docker' }
      steps {
        sh 'docker system prune -af || true'
      }
    }

    stage('6. Build & Push Backend') {
      when { changeset "**/app/**" }
      agent { label 'docker' }
      steps {
        deleteDir()
        unstash 'source'
        dir('app') {
          sh """
            docker-compose -f ../docker-compose.aws.backend.prod.yml build
            docker tag "${JENKINS_HOOK}_${BACKEND_CONTAINER_IMAGE_TAG}" "${BACKEND_IMAGE_TAG}"
            docker push "${BACKEND_IMAGE}:latest"
          """
        }
      }
    }

    stage('7. Deploy Backend') {
      when { changeset "**/app/**" }
      agent { label 'docker' }
      steps {
        echo "→ There are changes in app, redeploy backend"
        withCredentials([[
          $class: 'AmazonWebServicesCredentialsBinding',
          credentialsId: 'aws-ecr-creds'
        ]]) {
          sh '''
            docker run --rm \
              -e AWS_ACCESS_KEY_ID=$AWS_ACCESS_KEY_ID \
              -e AWS_SECRET_ACCESS_KEY=$AWS_SECRET_ACCESS_KEY \
              -e AWS_DEFAULT_REGION=$AWS_DEFAULT_REGION \
              amazon/aws-cli ecs update-service \
                --cluster $AWS_CLUSTER \
                --service $AWS_BACKEND_SERVICE \
                --force-new-deployment
          '''
        }
      }
    }

    stage('8. Verify Deployments') {
      agent { label 'docker' }
      steps {
        withCredentials([[
          $class: 'AmazonWebServicesCredentialsBinding',
          credentialsId: 'aws-ecr-creds'
        ]]) {
          script {
            def services = [env.AWS_BACKEND_SERVICE]
            services.each { svc ->
              echo "⏳ Waiting for ${svc} to complete deployment…"
              timeout(time: 10, unit: 'MINUTES') {
                waitUntil {
                  def state = sh(
                    script: """
                      docker run --rm \\
                        -e AWS_ACCESS_KEY_ID \\
                        -e AWS_SECRET_ACCESS_KEY \\
                        -e AWS_DEFAULT_REGION \\
                        amazon/aws-cli ecs describe-services \\
                          --cluster ${env.AWS_CLUSTER} \\
                          --services ${svc} \\
                          --query "services[0].deployments[?status=='PRIMARY'].rolloutState" \\
                          --output text
                    """,
                    returnStdout: true
                  ).trim()
                  
                  echo "→ ${svc} rolloutState = ${state}"
                    return (state == 'COMPLETED')
                  }
              }
              echo "✅ ${svc} deployment COMPLETED"
            }
            echo "✅ All deployments are COMPLETED"
          }
        }
      }
    }

    stage('9. Notify') {
      when { expression { currentBuild.currentResult == 'SUCCESS' } }
      steps {
        emailext(
          mimeType: 'text/html',
          subject: "✅ Build #${env.BUILD_NUMBER} Success – ${env.JOB_NAME}",
          to: '$DEFAULT_RECIPIENTS',
          from: 'Jenkins NWS CI/CD (Main Load Data) <nnws15815@gmail.com>',
          body: '''<!DOCTYPE html>
              <html>
                <head>
                  <style>
                    body { font-family: Arial, sans-serif; color: #333; }
                    .header { background: #004579; padding: 10px; color: white; }
                    .content { padding: 20px; }
                    .changelog { background: #f9f9f9; border: 1px solid #ddd; padding: 10px; }
                    .commit { margin-bottom: 8px; }
                    .commit-author { font-weight: bold; }
                    .footer { font-size: 0.8em; color: #777; margin-top: 20px; }
                  </style>
                </head>
                <body>
                  <div class="header">
                    Jenkins CI/CD Notification (Main Load data)
                  </div>
                  <div class="content">
                    <h1>Build #${BUILD_NUMBER} – Success 🎉</h1>
                    <p><strong>Project:</strong> ${JOB_NAME}</p>
                    <p><strong>URL:</strong> <a href="${BUILD_URL}">${BUILD_URL}</a></p>
                    
                    <h2>Commits included:</h2>
                    <div class="changelog">
                      <ul>
                        ${CHANGES, showPaths="true", format="<li class='commit'><span class='commit-author'>%a</span> – (<code>%r</code>)<br/><pre style='background:#eee;padding:8px;'>%m</pre><br/><small>Files:<br/>%p</small><br/></li>"}
                      </ul>
                    </div>
                  </div>
                  <div class="footer">
                    This is an automated message generated by Jenkins. Please contact DevOps Team for more questions.
                  </div>
                </body>
              </html>''',
        )
      }
    }
  } 

  post {
    failure {
      emailext(
        mimeType: 'text/html',
        subject: "❌ Build #${env.BUILD_NUMBER} Failed – ${env.JOB_NAME}",
        to: '$DEFAULT_RECIPIENTS',
        from: 'Jenkins NWS CI/CD (Main Load Data) <nnws15815@gmail.com>',
        body: '${FILE,path="failure_template.html"}'
      )
    }
  }
}    
