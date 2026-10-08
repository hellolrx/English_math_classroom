import { createApp } from 'vue'
import { createRouter, createWebHistory } from 'vue-router'
import App from './App.vue'
import './styles.css'
import LoginView from './views/LoginView.vue'
import TeacherHomeView from './views/TeacherHomeView.vue'
import QuestionSetsView from './views/QuestionSetsView.vue'
import QuestionSetDetailView from './views/QuestionSetDetailView.vue'
import SessionCreateView from './views/SessionCreateView.vue'
import TeacherSessionView from './views/TeacherSessionView.vue'
import StudentSessionView from './views/StudentSessionView.vue'
import ReportsView from './views/ReportsView.vue'
import StudentHomeView from './views/StudentHomeView.vue'
import StudentRoundView from './views/StudentRoundView.vue'
import StudentWordsView from './views/StudentWordsView.vue'
import TeacherWordsView from './views/TeacherWordsView.vue'

const router = createRouter({
  history: createWebHistory(),
  routes: [
    { path: '/', redirect: '/login' },
    { path: '/login', component: LoginView },
    { path: '/teacher', component: TeacherHomeView, meta: { requiresTeacher: true } },
    { path: '/teacher/question-sets', component: QuestionSetsView, meta: { requiresTeacher: true } },
    { path: '/teacher/question-sets/:id', component: QuestionSetDetailView, meta: { requiresTeacher: true } },
    { path: '/teacher/words', component: TeacherWordsView, meta: { requiresTeacher: true } },
    { path: '/teacher/sessions/new', component: SessionCreateView, meta: { requiresTeacher: true } },
    { path: '/teacher/sessions/:id', component: TeacherSessionView, meta: { requiresTeacher: true } },
    { path: '/teacher/reports', component: ReportsView, meta: { requiresTeacher: true } },
    { path: '/student', component: StudentHomeView, meta: { requiresStudent: true } },
    { path: '/student/words', component: StudentWordsView, meta: { requiresStudent: true } },
    { path: '/student/topics/:id', component: StudentRoundView, props: { mode: 'topic' }, meta: { requiresStudent: true } },
    { path: '/student/session/:token', component: StudentSessionView, meta: { requiresStudent: true } },
    { path: '/student/practice/:code', component: StudentRoundView, props: { mode: 'code' }, meta: { requiresStudent: true } },
  ],
})

router.beforeEach((to) => {
  if (to.meta.requiresTeacher && !localStorage.getItem('hhx_access_token')) {
    return { path: '/login', query: { redirect: to.fullPath } }
  }
  if (to.meta.requiresStudent && !localStorage.getItem('hhx_student_token')) return { path: '/login', query: { redirect: to.fullPath } }
})

createApp(App).use(router).mount('#app')
