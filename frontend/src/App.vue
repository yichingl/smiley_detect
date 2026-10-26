<script setup lang="ts">
  import { onMounted, ref } from 'vue'

  // interfaces
  interface InferenceImage {
    guid: string
    name: string
    filepath: string
    upload_group_id: string
    uploaded_at?: string
  }

  interface TaskInfo {
    guid: string
    detection_count: number
    task_status: string
    model_name?: string | null
  }

  interface Detection {
    id: number
    confidence: number
    x_min: number
    y_min: number
    x_max: number
    y_max: number
  }

  // variables
  const images = ref<InferenceImage[]>([])
  const expandedImages = ref<Record<string, boolean>>({})
  const imageDetails = ref<Record<string, TaskInfo[]>>({})

  // Track active detections and selected task ID per image
  const activeDetections = ref<Record<string, Detection[]>>({})
  const activeTaskId = ref<Record<string, string>>({})

  // Upload state variables
  const fileInput = ref<HTMLInputElement | null>(null)
  const selectedFile = ref<File | null>(null)
  const isUploading = ref(false)
  const uploadMessage = ref('')

  // Fetch existing uploaded images on mount / refresh
  const fetchImages = async () => {
    try {
      const response = await fetch('/images')
      if (response.ok) {
        images.value = await response.json()
      }
    } catch (err) {
      console.error('Failed to fetch images:', err)
    }
  }

  // Handle file selection
  const handleFileChange = (event: Event) => {
    const target = event.target as HTMLInputElement
    if (target.files && target.files[0]) {
      selectedFile.value = target.files[0]
    }
  }

  // Upload single image via /upload-single-image/
  const uploadImage = async () => {
    if (!selectedFile.value) {
      uploadMessage.value = 'Please select a file first!'
      return
    }

    const formData = new FormData()
    formData.append('file', selectedFile.value)

    isUploading.value = true
    uploadMessage.value = ''

    try {
      const response = await fetch('/upload-single-image/', {
        method: 'POST',
        body: formData,
      })

      if (!response.ok) {
        throw new Error('Upload failed')
      }

      uploadMessage.value = 'Image uploaded successfully!'
      selectedFile.value = null
      if (fileInput.value) fileInput.value.value = ''

      // Refresh images list automatically after upload
      await fetchImages()
    } catch (err) {
      uploadMessage.value = 'Error uploading image. Please try again.'
      console.error(err)
    } finally {
      isUploading.value = false
    }
  }

  // Fetch tasks for a specific image GUID (used for initial expansion and manual refresh)
  const fetchTasksForImage = async (imgGuid: string) => {
    try {
      const response = await fetch(`/images/${imgGuid}/tasks`)
      if (response.ok) {
        const data = await response.json()
        imageDetails.value[imgGuid] = data.tasks || []
      } else {
        imageDetails.value[imgGuid] = []
      }
    } catch (err) {
      console.error('Failed to fetch tasks for image', err)
      imageDetails.value[imgGuid] = []
    }
  }

  // Toggle expansion and lazily fetch tasks if not loaded yet
  const toggleExpand = async (img: InferenceImage) => {
    const currentState = !!expandedImages.value[img.guid]
    expandedImages.value[img.guid] = !currentState

    if (!currentState && !imageDetails.value[img.guid]) {
      await fetchTasksForImage(img.guid)
    }
  }

  // Start a task for the image guid
  const startTaskOnImage = async (imgGuid: string) => {
    try {
      const response = await fetch(`/process-image/${imgGuid}`, { method: 'POST' })
      if (!response.ok) {
        throw new Error(`Server returned status ${response.status}`)
      }
      // Automatically refresh tasks list after starting a new task
      await fetchTasksForImage(imgGuid)
    } catch (err) {
      console.error('Failed to start processing on image:', err)
    }
  }

  // Fetch task details and detections when a task item is clicked
  const selectTaskAndFetchDetections = async (imgGuid: string, task: TaskInfo) => {
    activeTaskId.value[imgGuid] = task.guid
    try {
      const response = await fetch(`/task-details/${task.guid}`)
      if (response.ok) {
        const data = await response.json()
        activeDetections.value[imgGuid] = data.detections || []
      } else {
        activeDetections.value[imgGuid] = []
      }
    } catch (err) {
      console.error('Failed to fetch task detections:', err)
      activeDetections.value[imgGuid] = []
    }
  }

  onMounted(() => {
    fetchImages()
  })
</script>

<template>
  <main class="dashboard">
    <div class="dashboard__shell">
      <header class="page-header">
        <div class="brand-mark" aria-hidden="true">S</div>
        <div class="page-header__copy">
          <p class="eyebrow">IMAGE ANALYSIS</p>
          <h1>Smiley Detection</h1>
          <p class="page-header__subtitle">Upload images, run detection, and review your results.</p>
        </div>
        <div class="image-count" aria-live="polite">
          <span class="image-count__value">{{ images.length }}</span>
          <span>{{ images.length === 1 ? 'image' : 'images' }} in library</span>
        </div>
      </header>

      <section class="panel upload-panel" aria-labelledby="upload-heading">
        <div class="section-heading">
          <div>
            <p class="eyebrow">GET STARTED</p>
            <h2 id="upload-heading">Add an image</h2>
            <p class="section-description">Choose a JPG or PNG image to run smiley detection.</p>
          </div>
          <span class="upload-icon" aria-hidden="true">↑</span>
        </div>

        <div class="upload-controls">
          <label class="file-picker" :class="{ 'file-picker--selected': selectedFile }">
            <input
              ref="fileInput"
              type="file"
              accept="image/jpeg, image/jpg, image/png"
              @change="handleFileChange"
            />
            <span class="file-picker__icon" aria-hidden="true">＋</span>
            <span class="file-picker__text">
              <strong>{{ selectedFile ? selectedFile.name : 'Choose an image' }}</strong>
              <small>{{ selectedFile ? 'Ready to upload' : 'JPG or PNG, select a file from your device' }}</small>
            </span>
            <span class="file-picker__action">Browse</span>
          </label>
          <button
            class="button button--primary upload-button"
            type="button"
            :disabled="isUploading || !selectedFile"
            @click="uploadImage"
          >
            <span v-if="isUploading" class="button-spinner" aria-hidden="true"></span>
            {{ isUploading ? 'Uploading' : 'Upload image' }}
          </button>
        </div>

        <p
          v-if="uploadMessage"
          class="feedback-message"
          :class="uploadMessage.includes('successfully') ? 'feedback-message--success' : 'feedback-message--error'"
          role="status"
        >
          {{ uploadMessage }}
        </p>
      </section>

      <section class="library-section" aria-labelledby="library-heading">
        <div class="library-heading">
          <div>
            <p class="eyebrow">YOUR WORKSPACE</p>
            <h2 id="library-heading">Image library</h2>
            <p class="section-description">Select an image to inspect it and manage detection tasks.</p>
          </div>
          <button class="button button--secondary" type="button" @click="fetchImages">
            <span aria-hidden="true">↻</span>
            Refresh
          </button>
        </div>

        <div v-if="images.length === 0" class="empty-state">
          <div class="empty-state__icon" aria-hidden="true">▧</div>
          <h3>Your library is empty</h3>
          <p>Upload an image above to get started. Your images and detection tasks will appear here.</p>
        </div>

        <div v-else class="image-list">
          <article v-for="img in images" :key="img.guid" class="image-card">
            <div class="image-card__summary">
              <button
                class="image-card__toggle"
                type="button"
                :aria-expanded="!!expandedImages[img.guid]"
                @click="toggleExpand(img)"
              >
                <img class="image-card__thumbnail" :src="`/${img.filepath}`" :alt="`Thumbnail of ${img.name}`" />
                <span class="image-card__details">
                  <strong class="image-card__name">{{ img.name }}</strong>
                  <span class="image-card__path">{{ img.filepath }}</span>
                </span>
                <span class="image-card__chevron" :class="{ 'image-card__chevron--expanded': expandedImages[img.guid] }" aria-hidden="true">
                  ⌄
                </span>
              </button>
              <span class="image-card__task-count">
                {{ imageDetails[img.guid]?.length ?? 0 }}
                {{ imageDetails[img.guid]?.length === 1 ? 'task' : 'tasks' }}
              </span>
            </div>

            <div v-if="expandedImages[img.guid]" class="image-card__content">
              <div class="image-overview">
                <div class="preview-frame">
                  <img
                    class="preview-frame__image"
                    :src="activeTaskId[img.guid] ? `/tasks/${activeTaskId[img.guid]}/rendered-image` : `/${img.filepath}`"
                    :alt="activeTaskId[img.guid] ? `Detection result for ${img.name}` : `Preview of ${img.name}`"
                  />
                  <span
                    v-if="activeTaskId[img.guid] && activeDetections[img.guid]?.length === 0"
                    class="preview-frame__badge"
                  >
                    No smileys detected
                  </span>
                </div>

                <div class="image-metadata">
                  <div class="image-metadata__heading">
                    <div>
                      <p class="eyebrow">IMAGE DETAILS</p>
                      <h3>{{ img.name }}</h3>
                    </div>
                    <button class="button button--primary" type="button" @click="startTaskOnImage(img.guid)">
                      Run detection
                    </button>
                  </div>
                  <dl class="metadata-list">
                    <div>
                      <dt>Uploaded</dt>
                      <dd>{{ img.uploaded_at ? new Date(img.uploaded_at).toLocaleString() : '--' }}</dd>
                    </div>
                    <div>
                      <dt>Image ID</dt>
                      <dd class="metadata-list__id">{{ img.guid }}</dd>
                    </div>
                    <div>
                      <dt>Upload group</dt>
                      <dd class="metadata-list__id">{{ img.upload_group_id }}</dd>
                    </div>
                  </dl>
                </div>
              </div>

              <div class="task-section">
                <div class="task-section__heading">
                  <div>
                    <h3>Detection tasks</h3>
                    <p class="section-description">Choose a task to view its result.</p>
                  </div>
                  <button class="button button--text" type="button" @click="fetchTasksForImage(img.guid)">
                    <span aria-hidden="true">↻</span>
                    Refresh tasks
                  </button>
                </div>

                <div v-if="!imageDetails[img.guid] || imageDetails[img.guid].length === 0" class="task-empty">
                  No tasks yet. Run detection to create the first task.
                </div>
                <ul v-else class="task-list">
                  <li v-for="task in imageDetails[img.guid]" :key="task.guid">
                    <button
                      class="task-row"
                      :class="{ 'task-row--active': activeTaskId[img.guid] === task.guid }"
                      type="button"
                      :aria-pressed="activeTaskId[img.guid] === task.guid"
                      @click="selectTaskAndFetchDetections(img.guid, task)"
                    >
                      <span class="task-row__main">
                        <span class="task-row__id">{{ task.guid }}</span>
                        <span class="task-row__model">{{ task.model_name || 'Model not recorded' }}</span>
                      </span>
                      <span class="task-row__metrics">
                        <span class="status-badge" :class="`status-badge--${task.task_status.toLowerCase()}`">
                          {{ task.task_status }}
                        </span>
                        <span class="detection-count">
                          <strong>{{ task.detection_count }}</strong>
                          {{ task.detection_count === 1 ? 'detection' : 'detections' }}
                        </span>
                      </span>
                    </button>
                  </li>
                </ul>
              </div>
            </div>
          </article>
        </div>
      </section>

      <footer class="page-footer">Smiley Detection <span aria-hidden="true">·</span> Image analysis workspace</footer>
    </div>
  </main>
</template>